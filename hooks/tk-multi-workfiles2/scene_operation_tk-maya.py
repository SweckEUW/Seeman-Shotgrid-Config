import sgtk
import maya.cmds as cmds
import os
import shutil
import re # Wichtig für Regex

# USD Imports (müssen im Environment verfügbar sein)
try:
    from pxr import Usd, Sdf
    import mayaUsd.lib
except ImportError:
    pass

Hook = sgtk.get_hook_baseclass()

class SceneOperation(Hook):

    def execute(self, operation, file_path, context, parent_action, file_version, read_only, **kwargs):
        """
        Haupt-Exekutions-Methode.
        """

        if operation == "open":
            # do new scene as Maya doesn't like opening 
            # the scene it currently has open!   
            cmds.file(new=True, force=True) 
            cmds.file(file_path, open=True, force=True, ignoreVersion=True)
 
        # Wir interessieren uns nur für das Erstellen einer neuen Datei ("New File")
        if operation == "prepare_new":
            
            # 1. Prüfen: Sind wir in einem Shot Context?
            if context.entity and context.entity["type"] == "Shot":
                self.logger.info("Shot Context erkannt. Starte USD Setup...")
                cmds.file(newFile=True, force=True)

                # Setup Scene
                cmds.currentUnit(linear='m')
                
                # --- ÄNDERUNG: Wir holen uns den Pfad aus der Setup-Funktion ---
                generated_usd_path = self._setup_usd_shot_structure(context)
                
                # Wenn wir einen Pfad zurückbekommen haben, laden wir ihn
                if generated_usd_path:
                    self._load_usd_file(context, generated_usd_path)
            else:
                self.logger.info("Kein Shot Context. Überspringe USD Setup.")

        # do new file:    
        return True
    
    def _setup_usd_shot_structure(self, context):
        """
        Erstellt die Shot USD Struktur.
        Gibt den Pfad zur Shot-Datei zurück (oder None bei Fehler).
        """
        
        # --- 1. PFADE AUFLÖSEN ---
        
        shot_stage_template = self.sgtk.templates.get("shot_stage_file")
        if not shot_stage_template:
            self.logger.error("Template 'shot_stage_file' nicht in templates.yml gefunden!")
            return None

        fields = context.as_template_fields(shot_stage_template)
        
        # --- FIX: FALLBACK FÜR LEERE FELDER (API ABFRAGE) ---
        if not fields.get("Sequence") or not fields.get("Shot"):
            self.logger.info("Fields sind leer (kein Path Cache). Hole Daten manuell via ShotGrid API...")
            
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
                self.logger.error(f"Fehler bei der API Abfrage: {e}")
        # ----------------------------------------------------

        # Zielpfad berechnen
        try:
            shot_usd_path = shot_stage_template.apply_fields(fields)
        except Exception as e:
            self.logger.error(f"Konnte Pfad nicht auflösen: {e}")
            return None
    
        # --- 2. SHOT DATEI ERSTELLEN (COPY BASE) ---
        usd_shot_base = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/Shot.usda" 
        
        if not os.path.exists(shot_usd_path):
            self.logger.info(f"Erstelle Shot Stage aus Base File: {shot_usd_path}")
            
            shot_dir = os.path.dirname(shot_usd_path)
            if not os.path.exists(shot_dir):
                os.makedirs(shot_dir)
                
            try:
                shutil.copy2(usd_shot_base, shot_usd_path)
            except IOError as e:
                self.logger.error(f"Fehler beim Kopieren der Base Datei: {e}")
                return None
        else:
            self.logger.info(f"Shot Stage existiert bereits: {shot_usd_path}")


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
                    self.logger.info(f"USD Prim umbenannt zu: {new_prim_name}")
                else:
                    self.logger.error(f"Konnte USD Prim '{old_prim_name}' nicht umbenennen.")
            else:
                 # Check if already renamed
                if layer.GetPrimAtPath(f"/{new_prim_name}"):
                    self.logger.info("Prim wurde anscheinend bereits umbenannt.")
                else:
                    self.logger.warning(f"Prim '{old_prim_name}' in Base File nicht gefunden!")


        # --- 4. LAYOUT DATEI ERSTELLEN ---
        layout_base = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/Layout.usda"
        publish_template = self.sgtk.templates.get("shot_publish")

        if publish_template:
            layout_fields = context.as_template_fields(publish_template)
            
            # Auch hier den Fallback anwenden, falls nötig
            if not layout_fields.get("Sequence") or not layout_fields.get("Shot"):
                layout_fields["Sequence"] = fields.get("Sequence")
                layout_fields["Shot"] = fields.get("Shot")

            layout_fields["Step"] = "Layout" 
            
            layout_publish_dir = publish_template.apply_fields(layout_fields)
            shot_name_clean = layout_fields.get("Shot", "Shot").replace(" ", "_")
            layout_filename = f"{shot_name_clean}_Layout_v001.usda"
            layout_target_path = os.path.join(layout_publish_dir, layout_filename)

            if not os.path.exists(layout_target_path):
                self.logger.info(f"Erstelle Layout Publish: {layout_target_path}")
                
                if not os.path.exists(layout_publish_dir):
                    try:
                        os.makedirs(layout_publish_dir)
                    except OSError:
                        pass
                
                try:
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
                    self.logger.error(f"Fehler Layout Copy: {e}")
            
            # --- 5. REFERENZ UPDATE IN SHOT.USD ---
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
                elif rel_path not in sublayers:
                     # Falls Layout ganz fehlt, optional hinzufügen
                     # layer.subLayerPaths.append(rel_path)
                     # layer.Save()
                     pass

        # --- WICHTIG: Pfad zurückgeben für die nächste Funktion ---
        return shot_usd_path

    # --- ÄNDERUNG: Pfad als Argument akzeptieren ---
    def _load_usd_file(self, context, shot_usd_path):
        """
        Lädt die Shot USD Datei in Maya.
        """
        
        # Wir müssen den Pfad hier NICHT mehr berechnen, er wird übergeben!
        
        # Sicherstellen, dass Pfad-Separatoren für Maya passen
        shot_usd_path = shot_usd_path.replace("\\", "/")
        
        if not os.path.exists(shot_usd_path):
            self.logger.error(f"Konnte Shot Datei nicht finden: {shot_usd_path}")
            return

        # --- MAYA USD PLUGIN LADEN ---
        plugins_to_check = ["mayaUsdPlugin", "pxrUsd"] 
        loaded = False
        for plugin in plugins_to_check:
            try:
                if not cmds.pluginInfo(plugin, query=True, loaded=True):
                    cmds.loadPlugin(plugin, quiet=True)
                loaded = True
                break 
            except:
                continue
        
        if not loaded:
            self.logger.warning("Konnte Maya USD Plugin nicht laden.")

        # --- STAGE ERSTELLEN ---
        self.logger.info(f"Lade USD Stage: {shot_usd_path}")
        
        stage_node_name = "Shot_Stage"
        
        try:
            shape_node = cmds.createNode("mayaUsdProxyShape", name=f"{stage_node_name}Shape")
        except RuntimeError:
            self.logger.error("Fehler: Node-Type 'mayaUsdProxyShape' unbekannt.")
            return

        cmds.setAttr(f"{shape_node}.filePath", shot_usd_path, type="string")
        cmds.connectAttr("time1.outTime", f"{shape_node}.time")

        # Transform Node sauber benennen
        parents = cmds.listRelatives(shape_node, parent=True, fullPath=True)
        if parents:
            transform_node = parents[0]
            if transform_node != stage_node_name:
                transform_node = cmds.rename(transform_node, stage_node_name)
                shape_node = cmds.listRelatives(transform_node, shapes=True, fullPath=True)[0]
        

        # --- DEPARTMENT LAYER ERSTELLEN ---
        try:
            # Stage aus Maya Node holen
            stage = mayaUsd.lib.GetPrim(shape_node).GetStage()
            
            if stage:
                self._setup_department_layer(stage, context, shot_usd_path)
            else:
                self.logger.error("Konnte USD Stage Objekt nicht aus Maya Node abrufen.")
                
        except Exception as e:
            self.logger.error(f"Fehler beim Setup des Department Layers: {e}")

    def _setup_department_layer(self, stage, context, shot_root_path):
        """
        Erstellt einen ANONYMOUS Layer (nur RAM).
        """
        step_name = context.step["name"] if context.step else "Common"
        step_name = step_name.replace(" ", "_")
        
        shot_filename = os.path.basename(shot_root_path)
        shot_name_only = os.path.splitext(shot_filename)[0]
        
        target_file_name = f"{shot_name_only}_{step_name}.usda"
        shot_dir = os.path.dirname(shot_root_path)
        target_file_path = os.path.join(shot_dir, target_file_name)

        if os.path.exists(target_file_path):
            dept_layer = Sdf.Layer.FindOrOpen(target_file_path)
            is_anonymous = False
            self.logger.info(f"Existierenden Department Layer geladen: {target_file_path}")

        else:
            dept_layer = Sdf.Layer.CreateAnonymous(target_file_name)
            dept_layer.customLayerData = {"target_save_path": target_file_path}
            is_anonymous = True
            self.logger.info(f"Anonymous Layer im Speicher erstellt: {dept_layer.identifier}")

        root_layer = stage.GetRootLayer()
        
        if is_anonymous:
            layer_id_to_add = dept_layer.identifier
        else:
            layer_id_to_add = Sdf.ComputeAssetPathRelativeToLayer(root_layer, target_file_path)

        if layer_id_to_add not in root_layer.subLayerPaths:
            root_layer.subLayerPaths.insert(0, layer_id_to_add)
            self.logger.info(f"Layer '{layer_id_to_add}' zur Stage hinzugefügt.")

        if dept_layer:
            stage.SetEditTarget(dept_layer)
            self.logger.info(f"*** EDIT TARGET GESETZT AUF: {step_name} ***")