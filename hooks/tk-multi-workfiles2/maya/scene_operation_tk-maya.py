import sgtk
import maya.cmds as cmds
import os
import shutil
from pxr import Sdf
import mayaUsd.lib as mayaUsdLib

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

                # 1. Setup USD Structure (Copy USD Shot Base & Layout file to correct locations)
                generated_usd_path = self._setup_usd_shot_structure(context)
                
                # 2. Load USD file into Maya
                shape_node = None
                if generated_usd_path:
                    shape_node = self._load_usd_file(context, generated_usd_path)

                # 3. Create Department Layer (Animation) in Maya USD Stage
                if shape_node:
                    self._setup_department_layer(shape_node, context, generated_usd_path)

            return True

        return True
    
    def _setup_usd_shot_structure(self, context):
        """
        Creates the Shot USD structure and overwrites existing files.
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
    
        # --- 2. CREATE SHOT FILE (FORCE OVERWRITE) ---
        usd_shot_base = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/Shot.usda" 
        
        shot_dir = os.path.dirname(shot_usd_path)
        if not os.path.exists(shot_dir):
            os.makedirs(shot_dir)
            
        try:
            # No 'if exists' check anymore -> Always overwrite
            self.logger.info(f"Overwriting Shot Stage with Base File: {shot_usd_path}")
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

        # --- 4. CREATE LAYOUT FILE (FORCE OVERWRITE) ---
        layout_base = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/Layout.usda"
        publish_template = self.sgtk.templates.get("shot_publish")

        if publish_template:
            layout_fields = fields.copy() # Use the already resolved fields
            layout_fields["Step"] = "Layout" 
            
            layout_publish_dir = publish_template.apply_fields(layout_fields).replace("\\", "/")
            shot_name_clean = layout_fields.get("Shot", "Shot").replace(" ", "_")
            layout_filename = f"{shot_name_clean}_Layout_v001.usda"
            layout_target_path = os.path.join(layout_publish_dir, layout_filename).replace("\\", "/")

            # Create folder
            if not os.path.exists(layout_publish_dir):
                try:
                    os.makedirs(layout_publish_dir)
                except OSError:
                    pass
            
            # Copy layout file (Always overwrite)
            try:
                self.logger.info(f"Overwriting Layout File: {layout_target_path}")
                shutil.copy2(layout_base, layout_target_path)
                
                # Rename in Layout File
                layout_layer = Sdf.Layer.FindOrOpen(layout_target_path)
                if layout_layer:
                    l_old_path = "/Shot"
                    if layout_layer.GetPrimAtPath(l_old_path):
                        l_edit = Sdf.BatchNamespaceEdit()
                        l_edit.Add(Sdf.NamespaceEdit.Rename(l_old_path, new_prim_name))
                        if layout_layer.CanApply(l_edit):
                            layout_layer.Apply(l_edit)
                            layout_layer.defaultPrim = new_prim_name
                            layout_layer.Save()
            except IOError as e:
                self.logger.error(f"Error Layout Copy: {e}")
            
            # --- 5. REFERENCE UPDATE IN SHOT.USD ---
            if layer:
                rel_path = Sdf.ComputeAssetPathRelativeToLayer(layer, layout_target_path)
                sublayers = layer.subLayerPaths
                updated = False
                new_sublayers = []
                
                for sl in sublayers:
                    if "Layout.usda" in sl:
                        new_sublayers.append(rel_path)
                        updated = True
                    else:
                        new_sublayers.append(sl)
                
                if updated:
                    layer.subLayerPaths.clear()
                    for sl in new_sublayers:
                        layer.subLayerPaths.append(sl)
                    layer.Save()

        return shot_usd_path

    def _load_usd_file(self, context, shot_usd_path):
        """
        Loads the Shot USD file. 
        Returns: The name of the created Shape Node (String) or None.
        """
        # Fix path
        shot_usd_path = shot_usd_path.replace("\\", "/")
        
        if not os.path.exists(shot_usd_path):
            self.logger.error(f"Could not find Shot file: {shot_usd_path}")
            return None

        # Load plugin
        if not cmds.pluginInfo("mayaUsdPlugin", query=True, loaded=True): cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        # Maya 2025 may not provide this module; keep conversion optional.
        try:
            import mayaUsdStageConversion
        except ImportError:
            mayaUsdStageConversion = None
            self.logger.info("mayaUsdStageConversion not available (expected in Maya 2025). Skipping axis/unit auto-conversion.")

        self.logger.info(f"Loading USD Stage: {shot_usd_path}")
        
        stage_node_name = "Shot_Stage"
        
        # Cleanup
        if cmds.objExists(stage_node_name): cmds.delete(stage_node_name)

        try:
            # Create proxy shape
            shape_node = cmds.createNode("mayaUsdProxyShape", name=f"{stage_node_name}Shape")
            
            # Rename transform
            parents = cmds.listRelatives(shape_node, parent=True, fullPath=True)
            transform_node = parents[0]
            cmds.rename(transform_node, stage_node_name)
            
            # Get shape
            shape_node = cmds.listRelatives(stage_node_name, shapes=True, fullPath=True)[0]
            
            # Set attrs
            cmds.setAttr(f"{shape_node}.filePath", shot_usd_path, type="string")
            cmds.connectAttr("time1.outTime", f"{shape_node}.time")
            
            # Auto-convert axis & units
            if mayaUsdStageConversion:
                mayaUsdStageConversion.convertUpAxisAndUnit(shape_node, True, True, "rotateScale")
            
            return shape_node
            
        except Exception as e:
            self.logger.error(f"Error creating USD nodes: {e}")
            return None

    def _setup_department_layer(self, shape_node, context, shot_root_path):
        """
        Creates a Department Layer and sets it as the Edit Target.
        Requires the shape_node to access the stage.
        """
        self.logger.info("Starting Department Layer Setup...")

        # Get Stage
        try:
            stage = mayaUsdLib.GetPrim(shape_node).GetStage()
        except Exception:
            self.logger.error("Could not retrieve Stage from Shape Node.")
            return

        if not stage:
            self.logger.error("Stage is None/Invalid.")
            return

        step_name = context.step["name"] if context.step else "Common"
        step_name = step_name.replace(" ", "_")
        
        shot_filename = os.path.basename(shot_root_path)
        shot_name_only = os.path.splitext(shot_filename)[0]
        
        target_file_name = f"{shot_name_only}_{step_name}.usda"
        shot_dir = os.path.dirname(shot_root_path)
        target_file_path = os.path.join(shot_dir, target_file_name).replace("\\", "/")

        # Create or load layer (Always reload/create)
        dept_layer = Sdf.Layer.FindOrOpen(target_file_path)
        if not dept_layer:
            # If file does not exist, create new one
            dept_layer = Sdf.Layer.CreateNew(target_file_path)
            self.logger.info(f"Created new Department Layer: {target_file_path}")
        else:
            self.logger.info(f"Found existing Department Layer: {target_file_path}")

        # Add sublayer to Root Stage
        root_layer = stage.GetRootLayer()
        rel_path = Sdf.ComputeAssetPathRelativeToLayer(root_layer, target_file_path)

        if rel_path not in root_layer.subLayerPaths:
            # Insert at 0 (Strongest opinion)
            root_layer.subLayerPaths.insert(0, rel_path)
            self.logger.info(f"Added Layer '{rel_path}' to Stage.")
        
        # Set Edit Target
        if dept_layer:
            stage.SetEditTarget(dept_layer)
            self.logger.info(f"*** EDIT TARGET SET TO: {step_name} ***")