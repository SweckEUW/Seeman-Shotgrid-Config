import hou
import sgtk
import os
from pxr import Sdf, UsdGeom

# Get the base class for ShotGrid publish plugins
HookBaseClass = sgtk.get_hook_baseclass()

class UsdLayerPublishPlugin(HookBaseClass):
    """
    Plugin for exporting USD Layers from Houdini.
    Creates a clean Component structure with References in a Master Stage file.
    """

    # --------------------------------------------------------------------------
    # UI & SETTINGS PROPERTIES
    # These properties are loaded by the Publisher UI at startup to visualize the plugin.
    # --------------------------------------------------------------------------

    @property
    def icon(self):
        """
        Defines the icon displayed in the Publisher UI.
        Called when initializing the Publisher.
        """

        return os.path.join(self.disk_location, os.pardir, "icons", "usd.png")

    @property
    def name(self):
        """
        The display name of the plugin in the UI.
        """

        return "Seacarus USD Export"

    @property
    def description(self):
        """
        The description text/tooltip in the UI.
        """

        return "Exports USD layers and updates the asset stage composition."

    @property
    def item_filters(self):
        """
        Determines which items this plugin is applied to.
        Called after the Collector has finished running.
        Here: Only items of type "houdini.usd.layer" trigger this plugin.
        """

        return ["houdini.usd.layer"]

    @property
    def settings(self) -> dict:
        """
        Defines the configuration settings this plugin expects from publish.yml.
        Called at Publisher startup.
        """

        base_settings = super().settings or {}
        usd_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published USD files.",
            },
            "Asset Template": {
                "type": "template",
                "default": "asset_stage_file", 
                "description": "Template path for the Master Asset USD file.",
            }
        }

        # Adds USD-specific settings to the default settings
        base_settings.update(usd_publish_settings)
        return base_settings

    # --------------------------------------------------------------------------
    # VALIDATION LOGIC
    # These methods check if the publish is possible at all.
    # --------------------------------------------------------------------------

    def accept(self, settings, item):
        """
        First check. Decides if the plugin should be active for this specific item.
        Returns: Dictionary with 'accepted': True/False.
        """

        return {"accepted": True, "checked": True}

    def validate(self, settings, item) -> bool:
        """
        Second, stricter check. Executed when the user clicks "Validate".
        Checks:
        1. Does the node still exist in Houdini?
        2. Can the save path be generated successfully?
        """

        # Get the node path stored by the Collector in the item
        node_path = item.properties.get("node_path")
        node = hou.node(node_path)

        # 1. Check: Does the node exist?
        if not node_path or not node:
            raise Exception("Validation Error: Node not found in Houdini scene!")
        
        # 2. check if 'seacarus_layer_start' node is connected as input
        required_input_type = "seacarus_layer_start"
        upstream_nodes = node.inputAncestors()
        
        input_found = False

        if upstream_nodes:
            for input_node in upstream_nodes:
                if input_node.type().name() == required_input_type:
                    input_found = True
                    break 
        
        if not input_found:
            raise Exception(f"The node must have an input of type '{required_input_type}'!")

        return True

    # --------------------------------------------------------------------------
    # MAIN PUBLISH LOGIC
    # --------------------------------------------------------------------------

    def publish(self, settings, item):
        """
        The main function. Executed when the user clicks "Publish".
        Runs the export, updates the stage, and registers everything in ShotGrid.
        """

        node_path = item.properties.get("node_path")
        export_node = hou.node(node_path)

        start_node = None
        required_input_type = "seacarus_layer_start"
        upstream_nodes = export_node.inputAncestors()
        
        if upstream_nodes:
            for input_node in upstream_nodes:
                if input_node.type().name() == required_input_type:
                    start_node = input_node
                    break 
                    
        department = start_node.parm("department").evalAsString()

        # 1. Get Template object from settings (Defined in templates.yml)
        template_setting = settings.get("Publish Template")
        publish_template = self.sgtk.templates.get(template_setting.value)

        # 2. Extract fields (keys) from the current context (e.g., Shot, Sequence, Step)
        fields = item.context.as_template_fields(publish_template)
        
        fields["Step"] = department

        # 3. Calculate Versioning:
        # Searches for all existing files on disk matching this template.
        skip_keys = ["version"]
        existing_paths = self.sgtk.paths_from_template(publish_template, fields, skip_keys)
        
        latest_version = 0
        for path in existing_paths:
            path_fields = publish_template.get_fields(path)
            if "version" in path_fields:
                v = path_fields.get("version")
                if v > latest_version:
                    latest_version = v
        
        # Set the new version
        version = latest_version + 1
        fields["version"] = version

        # 4. Generate the final path string
        publish_path = publish_template.apply_fields(fields)

        # TEMPORARY HARD-CODED PATH FOR TESTING
        # filename = os.path.basename(publish_path)
        # publish_path = "C:/Users/Simon Weck/Desktop/" + filename + "a" 

        # 5. IMPORTANT: Store data on the item so it is available later in the 'publish' step.
        item.properties["publish_path"] = publish_path
        item.properties["publish_version"] = version
        item.properties["asset_name"] = fields.get("Asset", "Asset") 

        # Create destination folder (if it doesn't exist)
        folder = os.path.dirname(publish_path)
        if not os.path.exists(folder):
            os.makedirs(folder)

        # Set Asset Name on HDA
        asset_name = item.properties.get("asset_name", "DefaultAsset")
        start_node.parm("asset_name").set(asset_name)

        # Set Publish Path
        export_node.parm("usd_export_path").set(publish_path)

        self.logger.info(f"Set USD Export Path to: {publish_path}")
        self.logger.info(f"Set Asset Name to: {asset_name}")

        # --------------------------------------------------
        # STEP A: Render (Export from Houdini)
        # --------------------------------------------------
        try:
            rop_node = export_node.node("rop_export")
            rop_node.render()
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            raise e
        
        # --------------------------------------------------
        # STEP B: Register in ShotGrid Database
        # --------------------------------------------------
        name = os.path.basename(publish_path)
        args = {
            "tk": self.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": publish_path,
            "name": name,
            "version_number": version,
            "published_file_type": "USD Layer" 
        }

        # # The actual API Call to ShotGrid
        layer_entity = sgtk.util.register_publish(**args)
        self.logger.info(f"Registering in ShotGrid: {name} as 'USD Layer' v{version}")

        # --------------------------------------------------
        # STEP C: Asset Stage Update (Merger)
        # --------------------------------------------------
        self.update_stage_composition(settings, item, publish_path, department, layer_entity)


    def finalize(self, settings, item):
        """
        Called at the very end when everything is finished.
        Good for cleanup or final logs.
        """

        self.logger.info("Finalizing USD Layer Export... done.")


    # -------------------------------------------------------------------------
    # STAGE UPDATE LOGIC (PURE VERSIONING)
    # -------------------------------------------------------------------------

    def update_stage_composition(self, settings, item, new_layer_path, department, layer_entity):
        """
        Lädt die letzte Version des Master-Assets, tauscht den Layer aus 
        und speichert es als NEUE Version ab.
        """

        # 1. Templates und Felder vorbereiten
        # ------------------------------------
        tmpl_name = settings.get("Asset Template").value or "asset_stage_file"
        tmpl_stage = self.sgtk.templates.get(tmpl_name)
        
        if not tmpl_stage:
            self.logger.warning(f"Template '{tmpl_name}' missing. Skipping Stage Update.")
            return

        fields = item.context.as_template_fields(tmpl_stage)
        
        # Fallback, falls Asset Name nicht im Context ist
        asset_name = item.properties.get("asset_name", "Asset")
        if "Asset" not in fields:
            fields["Asset"] = asset_name

        # 2. Versionierung berechnen (Scan disk for latest)
        # ------------------------------------
        skip_keys = ["version"]
        existing_paths = self.sgtk.paths_from_template(tmpl_stage, fields, skip_keys)
        
        latest_asset_version = 0
        previous_file_path = None
        
        # Wir suchen die höchste existierende Version auf der Platte
        for path in existing_paths:
            path_fields = tmpl_stage.get_fields(path)
            if "version" in path_fields:
                v = path_fields.get("version")
                if v > latest_asset_version:
                    latest_asset_version = v
                    previous_file_path = path 
        
        # Neue Version definieren
        new_asset_version = latest_asset_version + 1
        fields["version"] = new_asset_version
        
        # Der Pfad für die NEUE Datei, die wir gleich erstellen
        new_stage_path = tmpl_stage.apply_fields(fields)

        # TEMPORARY HARD-CODED PATH FOR TESTING
        # filename = os.path.basename(new_stage_path)
        # new_stage_path = "C:/Users/Simon Weck/Desktop/" + filename
        
        self.logger.info(f"Preparing Asset Update: v{latest_asset_version} -> v{new_asset_version}")
        self.logger.info(f"New Master File will be: {new_stage_path}")

        # Ordner erstellen, falls nötig
        folder = os.path.dirname(new_stage_path)
        if not os.path.exists(folder):
            os.makedirs(folder)

        # 3. USD Layer Handling (Laden vs. Neu erstellen)
        # ------------------------------------
        layer = None
        
        if previous_file_path and os.path.exists(previous_file_path):
            self.logger.info(f"Loading previous composition from: {previous_file_path}")
            try:
                # WICHTIG: FindOrOpen lädt die Datei in den RAM. 
                # Wir bearbeiten sie im RAM, überschreiben aber NICHT die alte Datei,
                # weil wir später 'Export(new_path)' benutzen.
                layer = Sdf.Layer.FindOrOpen(previous_file_path)
            except Exception as e:
                self.logger.warning(f"Could not open previous layer: {e}")
        
        if not layer:
            self.logger.info("No previous version found. Creating clean Stage.")
            layer = Sdf.Layer.CreateNew(new_stage_path) # Temporär, wird beim Export eh überschrieben
        
        # Metadaten sicherstellen (falls neue Datei oder falls alte Datei fehlerhaft war)
        layer.framesPerSecond = 24.0
        layer.timeCodesPerSecond = 24.0
        layer.upAxis = UsdGeom.Tokens.y 
        layer.defaultPrim = asset_name

        # Prim (Xform) holen oder erstellen
        prim_path = Sdf.Path(f"/{asset_name}")
        prim = layer.GetPrimAtPath(prim_path)
        if not prim:
            prim = Sdf.PrimSpec(layer, asset_name, Sdf.SpecifierDef, "Xform")

        # 4. Referenzen austauschen
        # ------------------------------------

        # Relativen Pfad berechnen (vom NEUEN Master Asset zum Layer)
        # USD mag relative Pfade ("./../../model/v002/model.usd") lieber als absolute
        rel_path = os.path.relpath(new_layer_path, os.path.dirname(new_stage_path))
        rel_path = rel_path.replace("\\", "/") # Windows Fix

        # Referenz-Liste bearbeiten
        refs = prim.referenceList
        current_items = list(refs.prependedItems)
        cleaned_items = []
        
        # Alles behalten, was NICHT das aktuelle Department ist
        for ref in current_items:
            # Wir prüfen, ob der Department-Tag im Pfad vorkommt
            if department.lower() not in ref.assetPath.lower():
                cleaned_items.append(ref)
            else:
                self.logger.info(f"Removing outdated reference: {ref.assetPath}")

        # Neue Referenz erstellen
        new_ref = Sdf.Reference(rel_path)
        
        # Sortierung: Modelling meist ganz unten (Basis), Shading darüber
        if department.lower() == "modelling":
            cleaned_items.append(new_ref) # Append = Hinten anfügen (wird zuerst evaluiert in USD prepended list logic ist tricky, aber meistens ist append hier 'schwächer')
        else:
            cleaned_items.insert(0, new_ref)

        # Liste leeren und neu befüllen
        refs.prependedItems.clear()
        for ref_item in cleaned_items: 
            refs.prependedItems.append(ref_item)

        # 5. Speichern & Registrieren
        # ------------------------------------
        
        # Export speichert den aktuellen State im RAM in eine NEUE Datei auf der Festplatte.
        # Die alte 'previous_file_path' bleibt unangetastet!
        self.logger.info(f"Saving new Master Asset version to: {new_stage_path}")
        layer.Export(new_stage_path)

        # ShotGrid Registrierung (Asset mit Dependency zum Layer)
        dependency_ids = []
        if layer_entity:
            dependency_ids.append(layer_entity["id"])

        self.logger.info("Registering Master Asset in ShotGrid...")
        
        asset_args = {
            "tk": self.sgtk,
            "context": item.context,
            "comment": f"Auto-update: Included {department} v{item.properties.get('layer_version', '?')}",
            "path": new_stage_path,
            "name": f"{asset_name} (Master)",
            "version_number": new_asset_version,
            "published_file_type": "USD Asset", 
            "dependency_ids": dependency_ids
        }

        sgtk.util.register_publish(**asset_args)