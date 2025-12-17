import hou
import sgtk
import os
# WICHTIG: UsdGeom hinzufügen für die Tokens (Y-Axis)
from pxr import Usd, Sdf, UsdGeom

HookBaseClass = sgtk.get_hook_baseclass()

class UsdLayerPublishPlugin(HookBaseClass):
    """
    Plugin zum Exportieren von USD Layers aus Houdini.
    Erstellt eine saubere Component-Structure mit References.
    """

    @property
    def icon(self):
        return os.path.join(self.disk_location, os.pardir, "icons", "usd.png")

    @property
    def name(self):
        return "Seacarus USD Export"

    @property
    def description(self):
        return "Exportiert USD Layer und updated die Asset Stage composition."

    @property
    def item_filters(self):
        return ["houdini.usd.layer"]

    @property
    def settings(self) -> dict:
        base_settings = super().settings or {}
        usd_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published USD files.",
            }
        }
        base_settings.update(usd_publish_settings)
        return base_settings

    def accept(self, settings, item):
        return {"accepted": True, "checked": True}

    def validate(self, settings, item) -> bool:
        node_path = item.properties.get("node_path")
        if not node_path or not hou.node(node_path):
            return {"action": "validate", "errors": ["HDA Node nicht mehr gefunden!"]}

        try:
            self.configure_item(settings, item)
        except Exception as e:
            import traceback
            self.logger.error(traceback.format_exc())
            return {"action": "validate", "errors": [f"Path Configuration Error: {e}"]}

        return {"action": "validate", "errors": []}

    def configure_item(self, settings, item):
        # 1. Template holen
        template_setting = settings.get("Publish Template")
        if not template_setting:
            raise ValueError("Publish Template setting is missing in YAML config!")
            
        publish_template = self.sgtk.templates.get(template_setting.value)
        if not publish_template:
            raise ValueError(f"Template '{template_setting.value}' not found in templates.yml")

        # 2. Felder aus Context holen
        fields = item.context.as_template_fields(publish_template)
        
        # 3. Versionierung
        skip_keys = ["version"]
        existing_paths = self.sgtk.paths_from_template(publish_template, fields, skip_keys)
        
        latest_version = 0
        for path in existing_paths:
            path_fields = publish_template.get_fields(path)
            if "version" in path_fields:
                v = path_fields.get("version")
                if v > latest_version:
                    latest_version = v
        
        fields["version"] = latest_version + 1

        # 4. Pfad generieren
        publish_path = publish_template.apply_fields(fields)

        # 5. Daten speichern
        item.properties["publish_path"] = publish_path
        item.properties["publish_version"] = fields["version"]
        item.properties["asset_name"] = fields.get("Asset", "Asset") 
        
        self.logger.info(f"Configured Item Path: {publish_path} (v{fields['version']:03d})")

    def publish(self, settings, item):
        node_path = item.properties.get("node_path")
        department = item.properties.get("department")
        hda_node = hou.node(node_path)
        
        # Safety Check
        publish_path = item.properties.get("publish_path")
        if not publish_path:
            self.logger.info("Publish path missing. Running configuration...")
            self.configure_item(settings, item)
            publish_path = item.properties.get("publish_path")
        
        version_number = item.properties.get("publish_version")

        # Ordner erstellen
        self.ensure_publish_folder_exists(publish_path)

        # A: Rendern
        try:
            self.logger.info(f"Rendering USD to: {publish_path}")
            rop_node = hda_node.node("rop_export")
            if not rop_node:
                raise Exception("Internal 'rop_export' node missing in HDA.")
            
            rop_node.parm("lopoutput").set(publish_path)
            rop_node.render()
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            raise e

        # B: Stage Update
        self.update_stage_composition(item, publish_path, department)

        # C: Register
        self._register_publish(item, publish_path, version_number)

    def finalize(self, settings, item):
        self.logger.info("Finalizing USD Layer Export... done.")

    def ensure_publish_folder_exists(self, path):
        if path is None:
            raise ValueError("Cannot create folder for None path")
        folder = os.path.dirname(path)
        if not os.path.exists(folder):
            os.makedirs(folder)

    # -------------------------------------------------------------------------
    # STAGE UPDATE LOGIC
    # -------------------------------------------------------------------------

    def update_stage_composition(self, item, new_layer_path, department):
        tmpl_stage = self.sgtk.templates.get("asset_stage_file")
        if not tmpl_stage:
            self.logger.warning("Template 'asset_stage_file' missing. Skipping Stage Update.")
            return

        fields = item.context.as_template_fields(tmpl_stage)
        stage_path = tmpl_stage.apply_fields(fields)
        asset_name = item.properties.get("asset_name", fields.get("Asset", "Asset"))
        
        self.logger.info(f"Updating Stage File: {stage_path}")
        self.ensure_publish_folder_exists(stage_path)

        # 1. Layer öffnen (RAM -> Disk -> Neu)
        layer = Sdf.Layer.Find(stage_path)
        if not layer:
            if os.path.exists(stage_path):
                layer = Sdf.Layer.FindOrOpen(stage_path)
            else:
                layer = Sdf.Layer.CreateNew(stage_path)

        # --- FIX 1: ALTE SUBLAYERS LÖSCHEN ---
        # Damit die Datei sauber bleibt und nicht Sublayers UND References mischt.
        layer.subLayerPaths.clear()
        # -------------------------------------

        # Metadata
        layer.framesPerSecond = 24.0
        layer.timeCodesPerSecond = 24.0
        layer.upAxis = UsdGeom.Tokens.y 
        layer.defaultPrim = asset_name

        # Root Prim (Xform)
        prim_path = Sdf.Path(f"/{asset_name}")
        prim = layer.GetPrimAtPath(prim_path)
        
        if not prim:
            prim = Sdf.PrimSpec(layer, asset_name, Sdf.SpecifierDef, "Xform")
        
        prim.kind = "component"

        # --- FIX 2: DEPARTMENT MAPPING (MDL vs modelling) ---
        # Wir müssen wissen, wie das Department im Dateipfad heißt, um alte Versionen zu finden.
        # Falls dein ShotGrid "Short Codes" nutzt:
        dept_mapping = {
            "modelling": "MDL",
            "surfacing": "SUR", # oder SHD, je nach Pipeline
            "groom": "GRM"
        }
        # Wir suchen nach "MDL" statt "modelling", falls vorhanden
        search_str = dept_mapping.get(department.lower(), department)
        # ----------------------------------------------------

        # Pfad berechnen
        rel_path = os.path.relpath(new_layer_path, os.path.dirname(stage_path))
        rel_path = rel_path.replace("\\", "/") 

        # References Logic
        refs = prim.referenceList
        current_items = list(refs.prependedItems)
        
        cleaned_items = []
        
        # Cleanup: Alte Versionen dieses Departments entfernen
        for ref in current_items:
            # Wir prüfen, ob der search_str (z.B. MDL) im Pfad vorkommt
            if search_str.lower() not in ref.assetPath.lower():
                cleaned_items.append(ref)
            else:
                self.logger.info(f"Removing old reference (Version Update): {ref.assetPath}")

        # Neue Referenz hinzufügen
        new_ref = Sdf.Reference(rel_path)
        
        # Sortierung: Modelling (MDL) nach unten
        if department and department.lower() == "modelling":
            cleaned_items.append(new_ref)
        else:
            cleaned_items.insert(0, new_ref)

        # Zurückschreiben
        refs.prependedItems.clear()
        # WICHTIG: Variable umbenannt von 'item' zu 'ref_item'
        for ref_item in cleaned_items: 
            refs.prependedItems.append(ref_item)

        layer.Save()

        self.logger.info(f"Registering Asset Composition in ShotGrid: {stage_path}")
        
        # Asset Name für den Display Name im Loader
        asset_name = item.properties.get("asset_name", "Asset")

        # Wir nutzen die Helper-Funktion, aber passen den Typ an
        self._register_publish(
            item=item, 
            path=stage_path, 
            version=None, # None lässt ShotGrid die nächste Version raten (v1, v2...)
            file_type="USD Asset", # WICHTIG: Damit der Loader es unter Assets findet!
            name=f"{asset_name} (Master)"
        )

    def _register_publish(self, item, path, version, file_type="USD Layer", name=None):
        """
        Registriert den Publish in ShotGrid.
        Jetzt flexibel mit file_type und name Support.
        """
        # Falls kein Name übergeben wurde, nehmen wir den Dateinamen
        if name is None:
            name = os.path.basename(path)
            
        # Falls keine Version übergeben wurde (z.B. bei Assets), nehmen wir die vom Item
        if version is None:
            version = item.properties.get("publish_version")

        args = {
            "tk": self.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": path,
            "name": name,
            "version_number": version,
            "published_file_type": file_type  # Hier wird der dynamische Typ verwendet
        }
        
        # Sicherheitscheck: Falls version immer noch None ist (sollte nicht passieren)
        if args["version_number"] is None:
             self.logger.warning("Version number is None during registration! Defaulting to 1.")
             args["version_number"] = 1

        self.logger.info(f"Registering in ShotGrid: {name} as {file_type} v{args['version_number']}")
        sgtk.util.register_publish(**args)