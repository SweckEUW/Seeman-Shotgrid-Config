import hou
import sgtk
import os
# IMPORTANT: Import UsdGeom for Tokens (Y-Axis) and Sdf/Usd for Layer-Editing
from pxr import Usd, Sdf, UsdGeom

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
        
        # Check: Does the node exist?
        if not node_path or not hou.node(node_path):
            return {"action": "validate", "errors": ["HDA Node not found anymore!"]}

        # Check: Can we generate paths? (Calls configure_item)
        try:
            self.configure_item(settings, item)
        except Exception as e:
            # If path calculation fails, show error in UI
            import traceback
            self.logger.error(traceback.format_exc())
            return {"action": "validate", "errors": [f"Path Configuration Error: {e}"]}

        # Everything OK
        return {"action": "validate", "errors": []}

    # --------------------------------------------------------------------------
    # CONFIGURATION (PATH CALCULATION)
    # --------------------------------------------------------------------------

    def configure_item(self, settings, item):
        """
        Calculates the save path and the version number.
        Called during 'validate' and 'publish'.
        """
        # 1. Get Template object from settings (Defined in templates.yml)
        template_setting = settings.get("Publish Template")
        if not template_setting:
            raise ValueError("Publish Template setting is missing in YAML config!")
            
        publish_template = self.sgtk.templates.get(template_setting.value)
        if not publish_template:
            raise ValueError(f"Template '{template_setting.value}' not found in templates.yml")

        # 2. Extract fields (keys) from the current context (e.g., Shot, Sequence, Step)
        fields = item.context.as_template_fields(publish_template)
        
        # 3. Calculate Versioning:
        # Searches for all existing files on disk matching this template.
        skip_keys = ["version"]
        existing_paths = self.sgtk.paths_from_template(publish_template, fields, skip_keys)
        
        latest_version = 0
        for path in existing_paths:
            # Extract the version from each found path
            path_fields = publish_template.get_fields(path)
            if "version" in path_fields:
                v = path_fields.get("version")
                if v > latest_version:
                    latest_version = v
        
        # Set the new version (Highest found + 1)
        fields["version"] = latest_version + 1

        # 4. Generate the final path string
        publish_path = publish_template.apply_fields(fields)

        # 5. IMPORTANT: Store data on the item so it is available later in the 'publish' step.
        item.properties["publish_path"] = publish_path
        item.properties["publish_version"] = fields["version"]
        # Fallback to "Asset" if no name is in context
        item.properties["asset_name"] = fields.get("Asset", "Asset") 
        
        self.logger.info(f"Configured Item Path: {publish_path} (v{fields['version']:03d})")

    # --------------------------------------------------------------------------
    # MAIN PUBLISH LOGIC
    # --------------------------------------------------------------------------

    def publish(self, settings, item):
        """
        The main function. Executed when the user clicks "Publish".
        Runs the export, updates the stage, and registers everything in ShotGrid.
        """
        node_path = item.properties.get("node_path")
        department = item.properties.get("department")
        hda_node = hou.node(node_path)
        
        # Safety Check: If configure_item hasn't run yet, run it now
        publish_path = item.properties.get("publish_path")
        if not publish_path:
            self.logger.info("Publish path missing. Running configuration...")
            self.configure_item(settings, item)
            publish_path = item.properties.get("publish_path")
        
        version_number = item.properties.get("publish_version")

        # Create destination folder (if it doesn't exist)
        self.ensure_publish_folder_exists(publish_path)

        # Set Asset Name on HDA
        asset_name = item.properties.get("asset_name", "DefaultAsset")
        hda_node.parm("asset_name").set(asset_name)

        # Set Publish Path
        hda_node.parm("usd_export_path").set(publish_path)
        # hda_node.parm("usd_export_path").set("C:/Users/Simon Weck/Desktop/test.usda")  # TEMPORARY HARD-CODED PATH FOR TESTING

        self.logger.info(f"Set USD Export Path to: {publish_path}")
        self.logger.info(f"Set Asset Name to: {asset_name}")

        # ... (Weiter mit Asset Name setzen und Rendern) ...

        # --------------------------------------------------
        # STEP A: Render (Export from Houdini)
        # --------------------------------------------------
        try:
            self.logger.info(f"Rendering USD to: {publish_path}")

            # render
            rop_node = hda_node.node("rop_export")
            rop_node.render()
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            raise e

        # --------------------------------------------------
        # STEP B: Asset Stage Update (Merger)
        # --------------------------------------------------
        # Calls the helper function that edits the Master USD file
        self.update_stage_composition(item, publish_path, department)

        # --------------------------------------------------
        # STEP C: Register in ShotGrid Database
        # --------------------------------------------------
        self._register_publish(item, publish_path, version_number)

    def finalize(self, settings, item):
        """
        Called at the very end when everything is finished.
        Good for cleanup or final logs.
        """
        self.logger.info("Finalizing USD Layer Export... done.")

    # --------------------------------------------------------------------------
    # HELPER FUNCTIONS
    # --------------------------------------------------------------------------

    def ensure_publish_folder_exists(self, path):
        """
        Helper: Recursively creates folders for a given file path.
        """
        if path is None:
            raise ValueError("Cannot create folder for None path")
        folder = os.path.dirname(path)
        if not os.path.exists(folder):
            os.makedirs(folder)

    # -------------------------------------------------------------------------
    # STAGE UPDATE LOGIC (USD COMPOSITION)
    # -------------------------------------------------------------------------

    def update_stage_composition(self, item, new_layer_path, department):
        """
        This function opens (or creates) the "Master" USD file (asset_stage_file),
        removes old versions of the current department, and adds the new version.
        """
        # Load template for the master file
        tmpl_stage = self.sgtk.templates.get("asset_stage_file")
        self.logger.info(f"Loading Stage Template: {tmpl_stage}")

        if not tmpl_stage:
            self.logger.warning("Template 'asset_stage_file' missing. Skipping Stage Update.")
            return

        # Calculate path for the master file
        fields = item.context.as_template_fields(tmpl_stage)

        # Workarround when "Asset" is not in context. TODO: Fix this properly.
        asset_name = item.properties.get("asset_name", "Asset")
        if "Asset" not in fields:
            fields["Asset"] = asset_name

        stage_path = tmpl_stage.apply_fields(fields)
        asset_name = item.properties.get("asset_name", fields.get("Asset", "Asset"))
        
        self.logger.info(f"Updating Stage File: {stage_path}")
        self.ensure_publish_folder_exists(stage_path)

        # 1. Open Layer: Try to find, otherwise open, otherwise create new
        layer = Sdf.Layer.Find(stage_path)
        if not layer:
            if os.path.exists(stage_path):
                layer = Sdf.Layer.FindOrOpen(stage_path)
            else:
                layer = Sdf.Layer.CreateNew(stage_path)

        # --- FIX 1: CLEAR OLD SUBLAYERS ---
        # Prevents mixing Sublayers and References (USD Best Practice)
        layer.subLayerPaths.clear()
        
        # Set USD Metadata (Important for Frame Rates and Axis)
        layer.framesPerSecond = 24.0
        layer.timeCodesPerSecond = 24.0
        layer.upAxis = UsdGeom.Tokens.y 
        layer.defaultPrim = asset_name

        # Create or get Root Prim (Xform)
        prim_path = Sdf.Path(f"/{asset_name}")
        prim = layer.GetPrimAtPath(prim_path)
        
        if not prim:
            prim = Sdf.PrimSpec(layer, asset_name, Sdf.SpecifierDef, "Xform")
        
        # Kind = Component marks it as an Asset in USD
        prim.kind = "component"

        # --- DEPARTMENT MAPPING ---
        # Translates ShotGrid names (e.g. "modelling") into file shortcodes (e.g. "MDL")
        # to correctly identify old references.
        dept_mapping = {
            "modelling": "MDL",
            "surfacing": "SUR", 
            "groom": "GRM"
        }
        search_str = dept_mapping.get(department.lower(), department)

        # Calculate relative path (USD prefers relative paths over absolute)
        rel_path = os.path.relpath(new_layer_path, os.path.dirname(stage_path))
        rel_path = rel_path.replace("/", "/") 

        # --- REFERENCES UPDATE LOGIC ---
        refs = prim.referenceList
        current_items = list(refs.prependedItems)
        
        cleaned_items = []
        
        # Loop through all existing references:
        # If a reference has "MDL" in the name and we are currently publishing "MDL",
        # the old one is skipped (not added to cleaned_items).
        for ref in current_items:
            if search_str.lower() not in ref.assetPath.lower():
                cleaned_items.append(ref)
            else:
                self.logger.info(f"Removing old reference (Version Update): {ref.assetPath}")

        # Create new reference
        new_ref = Sdf.Reference(rel_path)
        
        # Sorting Logic:
        # Modeling should often be the base (bottom of the list/composition),
        # Shading/Groom often above.
        if department and department.lower() == "modelling":
            cleaned_items.append(new_ref) # Append at the end
        else:
            cleaned_items.insert(0, new_ref) # Insert at the beginning (Stronger opinion)

        # Clear reference list and refill
        refs.prependedItems.clear()
        for ref_item in cleaned_items: 
            refs.prependedItems.append(ref_item)

        # Save Master File
        layer.Save()

        # Register the Master File in ShotGrid as well
        self.logger.info(f"Registering Asset Composition in ShotGrid: {stage_path}")
        
        asset_name = item.properties.get("asset_name", "Asset")

        self._register_publish(
            item=item, 
            path=stage_path, 
            version=None, # None = ShotGrid calculates the version for the master file itself
            file_type="USD Asset", # IMPORTANT: Change type so Loader recognizes it as Asset
            name=f"{asset_name} (Master)"
        )

    def _register_publish(self, item, path, version, file_type="USD Layer", name=None):
        """
        Helper: Sends the final data to the ShotGrid database.
        Makes the file visible to other users in the Loader.
        """
        # If no name is provided, use the filename
        if name is None:
            name = os.path.basename(path)
            
        # If no version is provided, use the item's version
        if version is None:
            version = item.properties.get("publish_version")

        args = {
            "tk": self.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": path,
            "name": name,
            "version_number": version,
            "published_file_type": file_type 
        }
        
        # Fallback: Version 1 if everything goes wrong
        if args["version_number"] is None:
             self.logger.warning("Version number is None during registration! Defaulting to 1.")
             args["version_number"] = 1

        self.logger.info(f"Registering in ShotGrid: {name} as {file_type} v{args['version_number']}")
        # The actual API Call to ShotGrid
        sgtk.util.register_publish(**args)