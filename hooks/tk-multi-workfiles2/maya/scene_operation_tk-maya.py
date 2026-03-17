import sgtk
import maya.cmds as cmds
import os
import shutil
from pxr import Sdf, Usd, UsdGeom
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
            step_name = context.step["name"] if context.step else ""
            if context.entity and context.entity["type"] == "Shot" and step_name == "Animation": # Only run for Animation step in Shots
                self.logger.info(f"Animation Task detected for {context.entity['name']}. Starting USD Setup...")

                # Adjust Maya Settings
                # ortho_cameras = ["perspShape", "topShape", "sideShape", "frontShape"]
                # for cam in ortho_cameras:
                #     if cmds.objExists(cam):
                #         cmds.setAttr(f"{cam}.nearClipPlane", 0.1)
                #         cmds.setAttr(f"{cam}.farClipPlane", 100000)
                # cmds.currentUnit(linear='meter')
                # cmds.optionVar(category='Settings', stringValue=('workingUnitLinear', 'm'))
                # cmds.savePrefs(general=True)
                        
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
            self.logger.info("mayaUsdStageConversion not available (expected in Maya 2025). Using fallback conversion.")

        self.logger.info(f"Loading USD Stage: {shot_usd_path}")

        stage_up_axis, meters_per_unit = self._read_usd_stage_metrics(shot_usd_path)
        self._fallback_sync_scene_axis_and_units(stage_up_axis, meters_per_unit)
        
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
            # if mayaUsdStageConversion:
            #     mayaUsdStageConversion.convertUpAxisAndUnit(shape_node, True, True, "rotateScale")
            # else:
            self._apply_maya2025_stage_scale_workaround(stage_node_name, meters_per_unit)
            
            return shape_node
            
        except Exception as e:
            self.logger.error(f"Error creating USD nodes: {e}")
            return None

    def _read_usd_stage_metrics(self, usd_path):
        """
        Reads up-axis and metersPerUnit metadata from a USD stage.
        """
        try:
            stage = Usd.Stage.Open(usd_path)
            if not stage:
                self.logger.warning("Could not open USD stage for metadata read.")
                return None, None

            return UsdGeom.GetStageUpAxis(stage), UsdGeom.GetStageMetersPerUnit(stage)
        except Exception as e:
            self.logger.warning(f"Could not read USD stage metadata: {e}")
            return None, None

    def _fallback_sync_scene_axis_and_units(self, stage_up_axis, meters_per_unit):
        """
        Maya fallback: align Maya scene up-axis + linear units from USD metadata.
        """
        try:
            # Sync up-axis (Y/Z)
            current_up_axis = cmds.upAxis(query=True, axis=True)
            if stage_up_axis in ("y", "z") and current_up_axis != stage_up_axis:
                cmds.upAxis(axis=stage_up_axis, rotateView=True)

            # Sync linear units based on metersPerUnit metadata.
            maya_linear_unit = self._meters_to_maya_linear_unit(meters_per_unit)
            if maya_linear_unit:
                current_linear_unit = cmds.currentUnit(query=True, linear=True)
                if current_linear_unit != maya_linear_unit:
                    cmds.currentUnit(linear=maya_linear_unit)

            self.logger.info(
                f"Fallback axis/unit sync applied: upAxis={stage_up_axis}, metersPerUnit={meters_per_unit}."
            )
        except Exception as e:
            self.logger.warning(f"Fallback axis/unit sync failed: {e}")

    def _apply_maya2025_stage_scale_workaround(self, stage_node_name, meters_per_unit):
        """
        Maya 2025 workaround for missing distance conversion support in mayaUsd.
        Applies a uniform scale on the stage transform to compensate.
        """
        try:
            if meters_per_unit is None:
                self.logger.warning("Scale workaround skipped: metersPerUnit is unavailable.")
                return

            maya_internal_meters = 0.01  # Maya internal linear unit is centimeters.
            scale_factor = meters_per_unit / maya_internal_meters

            # Keep identity when already in cm-authored USD.
            if abs(scale_factor - 1.0) < 1e-8:
                return

            if not cmds.objExists(stage_node_name):
                self.logger.warning("Scale workaround skipped: stage transform not found.")
                return

            cmds.setAttr(f"{stage_node_name}.scaleX", scale_factor)
            cmds.setAttr(f"{stage_node_name}.scaleY", scale_factor)
            cmds.setAttr(f"{stage_node_name}.scaleZ", scale_factor)
            self.logger.info(
                f"Applied Maya 2025 stage scale workaround: factor={scale_factor} (metersPerUnit={meters_per_unit})."
            )
        except Exception as e:
            self.logger.warning(f"Scale workaround failed: {e}")

    def _meters_to_maya_linear_unit(self, meters_per_unit):
        """
        Converts USD metersPerUnit values to Maya linear unit tokens.
        """
        # Common values in USD pipelines. Tolerance allows tiny float noise.
        candidates = [
            (1.0, "m"),
            (0.01, "cm"),
            (0.001, "mm"),
            (0.1, "dm"),
            (0.3048, "ft"),
            (0.0254, "in"),
        ]

        tolerance = 1e-8
        for value, maya_unit in candidates:
            if abs(meters_per_unit - value) <= tolerance:
                return maya_unit

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