import sgtk
import maya.OpenMayaUI as apiUI
import maya.cmds as cmds
import maya.mel as mel

HookBaseClass = sgtk.get_hook_baseclass()

try:
    from PySide2 import QtWidgets
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6 import QtWidgets
    from shiboken6 import wrapInstance


class Helper(HookBaseClass):
    """
    Helper hook implementation for the tk-maya engine.
    """

    def get_main_window(self):
        """
        Get the main window of the application
        """
        ptr = apiUI.MQtUtil.mainWindow()
        if ptr is not None:
            return wrapInstance(int(ptr), QtWidgets.QWidget)

    def get_file_path(self):
        """
        Get the file path of the currently opened file
        """
        return cmds.file(q=True, sn=True)

    def get_cut_data(self):
        """
        Get the frame range and fps of the currently opened file
        """
        return {
            "cut_in": cmds.playbackOptions(query=True, animationStartTime=True),
            "cut_out": cmds.playbackOptions(query=True, animationEndTime=True),
            "fps": mel.eval('currentTimeUnitToFPS'),
        }

    def save_file(self, path):
        """
        Save the file, optionally with a new path

        :param str path:    Path to save the workfile to
        """
        if path is not None:
            cmds.file(rename=path)
        cmds.file(save=True)

