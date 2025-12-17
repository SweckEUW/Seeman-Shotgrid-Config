# Copyright (c) 2015 Shotgun Software Inc.
# ... (Header bleibt gleich) ...

import os
import re # WICHTIG: Für Regex Namespace Cleanup
import sgtk
import maya.cmds as cmds
import maya.mel as mel

HookBaseClass = sgtk.get_hook_baseclass()

class MayaActions(HookBaseClass):

    def generate_actions(self, sg_publish_data, actions, ui_area):
        # ... (dein bestehender Code hier ist gut) ...
        # (Kopiere deinen generate_actions Code von oben hier rein)
        app = self.parent
        action_instances = []

        if "reference" in actions:
            action_instances.append(
                {"name": "reference", "params": None, "caption": "Create Reference", "description": "References the item."}
            )

        if "import" in actions:
            action_instances.append(
                {"name": "import", "params": None, "caption": "Import into Scene", "description": "Imports the item."}
            )

        return action_instances

    def execute_multiple_actions(self, actions):
        for single_action in actions:
            self.execute_action(single_action["name"], single_action["params"], single_action["sg_publish_data"])

    def execute_action(self, name, params, sg_publish_data):
        app = self.parent
        # resolve path
        path = self.get_publish_path(sg_publish_data)

        if name == "reference":
            self._reference(path, sg_publish_data)

        if name == "import":
            self._import(path, sg_publish_data)

    # ----------------------------------------------------------------------------------------
    # HELPER METHODS
    # ----------------------------------------------------------------------------------------

    def _reference(self, path, sg_publish_data):
        """
        Intelligente Reference Funktion.
        Entscheidet basierend auf Dateityp, was zu tun ist.
        """
        if not os.path.exists(path):
            raise Exception("File not found on disk - '%s'" % path)

        # 1. USD CHECK: Ist es eine USD Datei?
        # Wenn ja, nutzen wir NICHT Maya Reference, sondern Proxy Shape (das ist der moderne Reference Workflow)
        if path.lower().endswith((".usd", ".usda", ".usdc")):
            self.parent.log_info("USD file detected during Reference action. Switching to Proxy Shape loader.")
            self._create_usd_proxy_shape(path, sg_publish_data)
            return

        # 2. NAMESPACE CLEANUP
        # Erstelle Namespace aus Entity + Name
        raw_namespace = "%s_%s" % (
            sg_publish_data.get("entity", {}).get("name", "Asset"),
            sg_publish_data.get("name", "Publish"),
        )
        
        # WICHTIG: Entferne alle illegalen Zeichen (Klammern, Leerzeichen etc.)
        # Erlaubt sind nur a-z, A-Z, 0-9 und _
        namespace = re.sub(r'[^a-zA-Z0-9_]', '_', raw_namespace)
        
        # Doppelte Unterstriche entfernen (Kosmetik)
        namespace = re.sub(r'_{2,}', '_', namespace)

        # 3. STANDARD MAYA REFERENCE (.ma, .mb, .abc)
        cmds.file(
            path,
            reference=True,
            loadReferenceDepth="all",
            mergeNamespacesOnClash=False,
            namespace=namespace,
            returnNewNodes=True
        )

    def _create_usd_proxy_shape(self, path, sg_publish_data):
        """
        Lädt USD als Proxy Shape (Der 'Reference'-Ersatz für USD).
        """
        app = self.parent
        
        # Plugin sicherstellen
        if not cmds.pluginInfo('mayaUsdPlugin', query=True, loaded=True):
            try:
                cmds.loadPlugin('mayaUsdPlugin')
            except Exception as e:
                # Fallback Versuch wie im vorherigen Chat besprochen
                maya_ver = cmds.about(version=True)
                fallback_path = f"C:/Program Files/Autodesk/Maya{maya_ver}/bin/plug-ins/mayaUsdPlugin.mll"
                if os.path.exists(fallback_path):
                    try:
                        cmds.loadPlugin(fallback_path)
                    except:
                        app.log_error("Could not load mayaUsdPlugin.")
                        return
                else:
                    app.log_error("Could not load mayaUsdPlugin.")
                    return

        # Namen säubern
        raw_name = sg_publish_data.get("code", os.path.basename(path))
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name)

        # Nodes erstellen
        transform = cmds.createNode('transform', name=safe_name)
        shape = cmds.createNode('mayaUsdProxyShape', parent=transform, name=f"{safe_name}Shape")

        # Pfad setzen (Slashes fixen für Maya)
        cmds.setAttr(f"{shape}.filePath", path.replace("\\", "/"), type="string")
        
        # Zeit verbinden
        if not cmds.isConnected('time1.outTime', f"{shape}.time"):
            cmds.connectAttr('time1.outTime', f"{shape}.time")
            
        cmds.select(transform)

    def _import(self, path, sg_publish_data):
        if not os.path.exists(path):
            raise Exception("File not found on disk - '%s'" % path)
        
        # Auch beim Importieren könnte man für USD eine Sonderbehandlung einbauen,
        # aber cmds.file(i=True) funktioniert für USD meistens (convert to geo),
        # solange das Plugin geladen ist.
        
        cmds.file(path, i=True, returnNewNodes=True)