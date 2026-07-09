import sgtk
import maya.cmds as cmds
import os
import shutil
from pxr import Sdf

Hook = sgtk.get_hook_baseclass()

class SceneOperation(Hook):

    def execute(self, operation, file_path, context, parent_action, file_version, read_only, **kwargs):
        """
        Main execution method.
        """

        if operation == "open":
            cmds.file(new=True, force=True) 
            cmds.file(file_path, open=True, force=True, ignoreVersion=True)
            return True
        
        elif operation == "save":
            cmds.file(save=True)
            return True

        elif operation == "save_as":
            cmds.file(rename=file_path)
            maya_file_type = "mayaAscii" if file_path.lower().endswith(".ma") else "mayaBinary"
            cmds.file(save=True, force=True, type=maya_file_type)
            return True

        elif operation == "reset":
            cmds.file(new=True, force=True)
            return True

        elif operation == "prepare_new":
            # Load Maya Preset and save as tmp.mb in same directory
            preset_path = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/maya/Maya_Preset.mb"
            preset_path = preset_path.replace("\\", "/")
            
            if os.path.exists(preset_path):
                try:
                    # Open preset file
                    cmds.file(preset_path, open=True, force=True)
                    self.logger.info(f"Opened Maya Preset: {preset_path}")
                    
                    # Save as tmp.mb in same directory
                    preset_dir = os.path.dirname(preset_path)
                    tmp_path = os.path.join(preset_dir, "tmp.mb").replace("\\", "/")
                    cmds.file(rename=tmp_path)
                    cmds.file(save=True, force=True, type="mayaBinary")
                    self.logger.info(f"Saved as tmp to: {tmp_path}")
                    
                except Exception as e:
                    self.logger.error(f"Error opening/saving preset: {e}")
                    cmds.file(new=True, force=True)
            else:
                self.logger.warning(f"Maya Preset not found: {preset_path}")
                cmds.file(new=True, force=True)
            
            step_name = context.step["name"] if context.step else ""
            if context.entity and context.entity["type"] == "Shot" and step_name == "Animation": # Only run for Animation step in Shots
                self.logger.info(f"Animation Task detected for {context.entity['name']}. Starting USD Setup...")

                # Create the Shot.usda assembly file (no Layout, no Maya stage).
                # Animation is layered into the Shot stage later, at publish time.
                self._setup_usd_shot_structure(context)

            return True

        return True
    
    def _setup_usd_shot_structure(self, context):
        """
        Creates the Shot.usda assembly file from the base template if it does
        not already exist, and names its default prim after the shot.
        """
        
        # --- 1. RESOLVE PATHS ---
        shot_stage_template = self.sgtk.templates.get("shot_stage_file")
        if not shot_stage_template:
            self.logger.error("Template 'shot_stage_file' not found in templates.yml!")
            return None

        fields = context.as_template_fields(shot_stage_template)
        
        # --- FIX: FALLBACK FOR EMPTY FIELDS (API QUERY) ---
        if not fields.get("Sequence") or not fields.get("Shot"):
            if context.entity:
                fields["Shot"] = context.entity["name"]
            
            try:
                sg = self.parent.shotgun
                shot_data = sg.find_one(
                    "Shot", 
                    [["id", "is", context.entity["id"]]], 
                    ["sg_sequence"]
                )
                
                if shot_data and shot_data.get("sg_sequence"):
                    fields["Sequence"] = shot_data["sg_sequence"]["name"]
                else:
                    fields["Sequence"] = "Common" 

            except Exception as e:
                self.logger.error(f"Error during API query: {e}")

        # Calculate target path & normalize backslashes
        try:
            shot_usd_path = shot_stage_template.apply_fields(fields)
            shot_usd_path = shot_usd_path.replace("\\", "/")
        except Exception as e:
            self.logger.error(f"Could not resolve path: {e}")
            return None
    
        # --- 2. CREATE SHOT FILE (ONLY IF MISSING) ---
        # Don't overwrite: an existing Shot.usda may already hold published animation layers.
        if os.path.exists(shot_usd_path):
            self.logger.info(f"Shot Stage already exists, leaving untouched: {shot_usd_path}")
            return shot_usd_path

        usd_shot_base = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/Shot.usda"

        shot_dir = os.path.dirname(shot_usd_path)
        if not os.path.exists(shot_dir):
            os.makedirs(shot_dir)

        try:
            self.logger.info(f"Creating Shot Stage from Base File: {shot_usd_path}")
            shutil.copy2(usd_shot_base, shot_usd_path)
        except IOError as e:
            self.logger.error(f"Error copying Base file: {e}")
            return None

        # --- 3. RENAME (Shot -> Sequence_Shot) ---
        seq_name = fields.get("Sequence", "Seq").replace(" ", "_")
        shot_name = fields.get("Shot", "Shot").replace(" ", "_")
        new_prim_name = f"{seq_name}_{shot_name}"
        
        layer = Sdf.Layer.FindOrOpen(shot_usd_path)
        
        if layer:
            old_prim_name = "Shot"
            old_prim_path = f"/{old_prim_name}"
            
            if layer.GetPrimAtPath(old_prim_path):
                edit = Sdf.BatchNamespaceEdit()
                edit.Add(Sdf.NamespaceEdit.Rename(old_prim_path, new_prim_name))
                
                if layer.CanApply(edit):
                    layer.Apply(edit)
                    layer.defaultPrim = new_prim_name
                    layer.Save()
                    self.logger.info(f"Renamed USD Prim to: {new_prim_name}")
                else:
                    self.logger.error(f"Could not rename USD Prim '{old_prim_name}'.")

        return shot_usd_path