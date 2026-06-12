import sgtk

try:
    from PySide2 import QtCore, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtWidgets

HookBaseClass = sgtk.get_hook_baseclass()


class Progress(HookBaseClass):
    """
    Progress hook.

    Shows a Qt QProgressDialog. Qt (PySide2/PySide6) is available in every engine
    this app runs in (Maya, Houdini, ...), so a single implementation works
    everywhere. The only engine-specific part -- the parent window -- is provided
    by the helper hook's get_main_window(), which is why no per-engine progress
    hook is needed.
    """

    # Each whole step is split into this many ticks so the bar can advance
    # smoothly within a step (e.g. per playblast / ffmpeg frame).
    _SCALE = 1000

    def __init__(self, *args, **kwargs):
        super(Progress, self).__init__(*args, **kwargs)
        self.__app = self.parent

        self.name = ""
        self.long_name = ""
        self.total_items = 1
        self.current_item = 0
        self.current_description = ""
        self.current_fraction = 0.0

        self._dialog = None

    def create_progress(self, name, long_name, total_items):
        """
        Create the progress instance

        :param str name:        Short progress name
        :param str long_name:   Long progress name
        :param int total_items: Total items in progress

        :returns:               Progress object
        :rtype:                 Progress
        """
        self.name = name
        self.long_name = long_name
        self.total_items = total_items
        return self

    def set_progress(self, current_item, description, fraction=0.0):
        """
        Set the current item index and description

        :param int current_item:    Progress item index
        :param str description:     Progress item description
        :param float fraction:      Sub-progress within the current step (0.0-1.0).
                                    Lets the bar fill smoothly toward the next step
                                    instead of only jumping when the step changes.
        """
        self.current_item = current_item
        self.current_description = description
        self.current_fraction = fraction

        self.__update()

    def next_progress(self, description):
        """
        Go to the next progress item

        :param str description: Progress item description
        """
        self.current_item += 1
        self.current_description = description
        self.current_fraction = 0.0

        self.__update()

    def finish(self):
        """
        Complete the progress
        """
        self.current_item = self.total_items
        self.current_fraction = 0.0

        self.__update()

    def start(self, callback):
        """
        Start the progress

        :param function callback: Callback on update

        :returns:               If progress succeeded
        :rtype:                 bool
        """
        self._dialog = QtWidgets.QProgressDialog(self.__get_main_window())
        self._dialog.setWindowTitle(self.name)
        self._dialog.setLabelText(self.long_name)
        self._dialog.setCancelButton(None)
        self._dialog.setMinimum(0)
        self._dialog.setMaximum(self.total_items * self._SCALE)
        self._dialog.setValue(0)
        self._dialog.setWindowModality(QtCore.Qt.NonModal)
        # The playblast grabs focus on the host main window while rendering, which
        # would push the dialog behind it. WindowStaysOnTopHint keeps it visible.
        self._dialog.setWindowFlags(
            self._dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint
        )
        # Show immediately instead of waiting on QProgressDialog's internal timer,
        # and don't let it auto-close/reset when it reaches the maximum.
        self._dialog.setMinimumDuration(0)
        self._dialog.setAutoClose(False)
        self._dialog.setAutoReset(False)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        QtWidgets.QApplication.processEvents()

        try:
            callback(self)
        finally:
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None

    def __get_main_window(self):
        """
        Get the host application's main window to parent the dialog to. The
        per-engine implementation lives in the helper hook.
        """
        try:
            return self.parent.execute_hook_method("helper_hook", "get_main_window")
        except Exception:
            return None

    def __update(self):
        """
        Call an update on the progress
        """
        if self._dialog is None:
            return

        maximum = self.total_items * self._SCALE
        value = int((self.current_item + self.current_fraction) * self._SCALE)

        self._dialog.setMaximum(maximum)
        self._dialog.setValue(min(value, maximum))
        self._dialog.setLabelText(
            "{} ({}/{})".format(
                self.current_description, self.current_item + 1, self.total_items + 1
            )
        )
        self._dialog.raise_()
        QtWidgets.QApplication.processEvents()
