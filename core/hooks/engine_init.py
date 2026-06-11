import sys
import tank

_STUDIO_LIBRARY_PATH = "X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/tools/StudioPoseLibrary/StudioPoseLibaryCore/src"


class EngineInit(tank.Hook):
    def execute(self, engine, **kwargs):
        if engine.name != "tk-maya":
            return

        if _STUDIO_LIBRARY_PATH not in sys.path:
            sys.path.insert(0, _STUDIO_LIBRARY_PATH)

        import maya.utils
        maya.utils.executeDeferred(_create_seacarus_shelf)


def _create_seacarus_shelf():
    import maya.cmds as cmds
    import maya.mel as mel

    shelf_name = "Seacarus"
    button_label = "PoseLibrary"
    open_cmd = (
        'import studiolibrary; '
        'studiolibrary.main('
        'name="Seacarus", '
        'path="X:/Projekte/MedienprojektSeemann/Seacarus/00_pipeline/tools/StudioPoseLibrary/Poses"'
        ')'
    )

    if not cmds.shelfLayout(shelf_name, exists=True):
        mel.eval(f'addNewShelfTab("{shelf_name}")')

    existing = cmds.shelfLayout(shelf_name, query=True, childArray=True) or []
    for btn in existing:
        try:
            if cmds.shelfButton(btn, query=True, label=True) == button_label:
                cmds.shelfButton(btn, edit=True, command=open_cmd)
                return
        except Exception:
            pass

    cmds.setParent(shelf_name)
    cmds.shelfButton(
        label=button_label,
        command=open_cmd,
        image="pythonFamily.png",
        annotation="Open Studio Pose Library",
        style="iconOnly",
    )