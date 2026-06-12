# MIT License

# Copyright (c) 2020 Netherlands Film Academy

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import sgtk

try:
    from PySide2 import QtCore
except ImportError:
    from PySide6 import QtCore


LATEST_VERSIONS_PLAYLIST = "Latest Versions"


class SubmitVersion(object):
    def __init__(self, app, file_path, frame_range, description):
        self.app = app
        self.file = file_path
        self.frame_range = frame_range
        self.description = description

    def submit_version(self):
        """Create a Version entity in ShotGrid, upload the movie, and
        optionally keep the 'Latest Versions' playlist up to date."""
        user = sgtk.util.get_current_user(self.app.sgtk)
        name = os.path.splitext(os.path.basename(self.file))[0]
        ctx = self.app.context

        data = {
            "code": name,
            "sg_status_list": "rev",
            "entity": ctx.entity,
            "sg_task": ctx.task,
            "sg_first_frame": self.frame_range[0],
            "sg_last_frame": self.frame_range[1],
            "sg_frames_have_slate": False,
            "created_by": user,
            "user": user,
            "description": self.description,
            "sg_movie_has_slate": True,
            "project": ctx.project,
            "frame_count": self.frame_range[1] - self.frame_range[0] + 1,
            "frame_range": "%s-%s" % (self.frame_range[0], self.frame_range[1]),
            "sg_path_to_movie": self.file,
        }

        try:
            version = self.app.sgtk.shotgun.create("Version", data)
            self.app.logger.debug("Created version in ShotGrid: %s" % str(data))

            self.__upload_version(version)
            self.app.logger.debug("Uploaded version to ShotGrid")

            # if self.app.get_setting("auto_update_playlist"):
            #     self._update_latest_playlist(version)

        except Exception as err:
            self.app.logger.debug(
                "An error occurred while creating a new version: {}".format(err)
            )

    def _update_latest_playlist(self, version):
        """Keep the 'Latest Versions' playlist to exactly one Version per
        Shot/Asset: remove any existing versions for this entity and add the
        newly published one.
        """
        sg = self.app.sgtk.shotgun
        project = self.app.context.project
        entity = self.app.context.entity

        if not entity:
            self.app.logger.debug(
                "No entity in context — skipping playlist update."
            )
            return

        try:
            playlist = sg.find_one(
                "Playlist",
                [["project", "is", project], ["code", "is", LATEST_VERSIONS_PLAYLIST]],
                ["versions"],
            )

            if not playlist:
                sg.create("Playlist", {
                    "code": LATEST_VERSIONS_PLAYLIST,
                    "project": project,
                    "versions": [{"type": "Version", "id": version["id"]}],
                })
                self.app.logger.debug(
                    "Created '%s' playlist with version %s."
                    % (LATEST_VERSIONS_PLAYLIST, version["id"])
                )
                return

            current_versions = playlist.get("versions") or []
            current_ids = [v["id"] for v in current_versions]

            # Find which versions in the playlist belong to the same entity
            stale_versions = sg.find(
                "Version",
                [["entity", "is", entity], ["id", "in", current_ids]],
                ["id"],
            ) if current_ids else []
            stale_ids = {v["id"] for v in stale_versions}

            updated = [v for v in current_versions if v["id"] not in stale_ids]
            updated.append({"type": "Version", "id": version["id"]})

            sg.update("Playlist", playlist["id"], {"versions": updated})
            self.app.logger.debug(
                "Updated '%s' playlist: removed %d stale version(s), added version %s."
                % (LATEST_VERSIONS_PLAYLIST, len(stale_ids), version["id"])
            )

        except Exception as err:
            # Playlist update is non-critical — log but don't abort
            self.app.logger.warning(
                "Could not update '%s' playlist: %s" % (LATEST_VERSIONS_PLAYLIST, err)
            )

    def __upload_version(self, version):
        """Upload the movie file to ShotGrid in a background thread."""
        event_loop = QtCore.QEventLoop()

        thread = UploaderThread(self.app, version, self.file)
        thread.finished.connect(event_loop.quit)
        thread.start()
        event_loop.exec_()

        if thread.get_errors():
            for e in thread.get_errors():
                self.app.logger.error(e)


class UploaderThread(QtCore.QThread):
    def __init__(self, app, version, filePath):
        QtCore.QThread.__init__(self)
        self.app = app
        self.version = version
        self.file = filePath
        self._errors = []

    def get_errors(self):
        return self._errors

    def run(self):
        try:
            self.app.sgtk.shotgun.upload(
                "Version", self.version["id"], self.file, "sg_uploaded_movie"
            )
        except Exception as e:
            self._errors.append("Movie upload to ShotGrid failed: %s" % e)
