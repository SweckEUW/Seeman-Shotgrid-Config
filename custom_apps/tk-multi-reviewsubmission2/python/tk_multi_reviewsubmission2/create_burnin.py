import datetime
import os
import subprocess
import threading

import sgtk

class CreateBurnin(object):
    def __init__(self, app):
        self.app = app
        
        # Set OS specific FFmpeg path
        if sgtk.util.is_linux(): self.ffmpeg_path = app.get_setting("ffmpeg_path_linux")
        elif sgtk.util.is_macos(): self.ffmpeg_path = app.get_setting("ffmpeg_path_mac")
        elif sgtk.util.is_windows(): self.ffmpeg_path = app.get_setting("ffmpeg_path_windows")

    def format_path_for_ffmpeg(self, file_path):
        # Convert Windows backslashes to forward slashes
        return file_path.replace("\\", "/")

    def format_font_path_for_ffmpeg(self, font_path):
        # Format path and double escape drive colon
        forward_slash_path = self.format_path_for_ffmpeg(font_path)
        return forward_slash_path.replace(":", "\\\\:")

    def escape_text_for_drawtext(self, text_string):
        # Escape special characters for FFmpeg drawtext filter
        if text_string is None: return ""
            
        safe_string = str(text_string)
        safe_string = safe_string.replace("\\", "\\\\")
        safe_string = safe_string.replace("'", "\\'")
        safe_string = safe_string.replace(":", "\\:")
        safe_string = safe_string.replace("[", "\\[")
        safe_string = safe_string.replace("]", "\\]")
        safe_string = safe_string.replace(",", "\\,")
        safe_string = safe_string.replace(";", "\\;")
        
        return safe_string

    def build_drawtext_string(self, text, x_pos, y_pos, font_argument, font_size=28, text_color="white"):
        # Create a single drawtext filter command
        safe_text = self.escape_text_for_drawtext(text)
        
        filter_string = "drawtext="
        filter_string += font_argument
        filter_string += "fontsize=" + str(font_size) + ":"
        filter_string += "fontcolor=" + text_color + ":"
        filter_string += "x=" + str(x_pos) + ":"
        filter_string += "y=" + str(y_pos) + ":"
        filter_string += "text='" + safe_text + "':"
        filter_string += "shadowx=2:shadowy=2:shadowcolor=black@0.7"
        
        return filter_string

    def get_system_font(self):
        # Find a valid font file on the system
        bundled_font = os.path.join(self.app.disk_location, "resources", "fonts", "DejaVuSans.ttf")
        if os.path.isfile(bundled_font): return "fontfile=" + self.format_font_path_for_ffmpeg(bundled_font) + ":"

        possible_fonts = []
        if sgtk.util.is_windows(): possible_fonts = [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\Arial.ttf"]
        elif sgtk.util.is_linux(): possible_fonts = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]

        for font_path in possible_fonts:
            if os.path.isfile(font_path): return "fontfile=" + self.format_font_path_for_ffmpeg(font_path) + ":"

        # Fallback to FFmpeg default font
        return ""

    def run_burnin(self, input_file, output_file, project_file, settings, on_ffmpeg_progress=None):
        # Create output directory
        output_dir = os.path.dirname(os.path.abspath(output_file))
        self.app.ensure_folder_exists(output_dir)

        # Extract settings into readable variables
        context = self.app.context
        company_name = self.app.get_setting("company_name")
        project_name = context.project["name"]
        user_name = context.user["name"]
        
        first_frame = int(settings["frame_range"][0])
        last_frame = int(settings["frame_range"][1])
        total_frames = last_frame - first_frame + 1
        
        task_name = context.step["name"] if context.step else ""
        description = settings.get("description", "") or ""
        fps = float(settings["fps"])
        version_number = int(settings["version"])
        
        video_width = int(settings["resolution"][0])
        video_height = int(settings["resolution"][1])

        # Format text elements
        version_string = "v00" + str(version_number) if version_number < 10 else "v0" + str(version_number)
        if task_name: version_label = task_name + " " + version_string
        else: version_label = version_string
            
        current_date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        resolution_label = str(video_width) + " x " + str(video_height)

        # Prepare FFmpeg file paths
        padded_input_file = input_file.replace("####", "%04d").replace("$F4", "%04d")
        ffmpeg_input_path = self.format_path_for_ffmpeg(padded_input_file)
        ffmpeg_output_path = self.format_path_for_ffmpeg(output_file)

        # Setup layout variables
        font_argument = self.get_system_font()
        margin = 30
        line_height = 40

        # Helper function for easier text creation
        def create_text(text, x, y, size=28, color="white"):
            return self.build_drawtext_string(text, x, y, font_argument, size, color)

        # Build the Burn-ins (for the video frames)
        burnin_elements = []
        burnin_elements.append(create_text(version_label, margin, "h-" + str(margin + line_height), 22))
        burnin_elements.append(create_text(user_name, "(w-tw)/2", "h-" + str(margin + line_height), 20, "white@0.65"))
        
        # Frame counter requires dynamic expression
        frame_offset = first_frame - 1
        frame_expression = "%{eif\\:n+" + str(frame_offset) + "\\:d}"
        
        frame_counter_filter = "drawtext=" + font_argument + "fontsize=22:fontcolor=white:"
        frame_counter_filter += "x=w-" + str(margin) + "-tw:y=h-" + str(margin + line_height) + ":"
        frame_counter_filter += "text='" + frame_expression + "':"
        frame_counter_filter += "shadowx=2:shadowy=2:shadowcolor=black@0.7"
        
        burnin_elements.append(frame_counter_filter)

        burnin_filter_chain = ",".join(burnin_elements)

        # 3. Combine everything into the filter_complex string
        filter_complex = "[0:v]" + burnin_filter_chain + "[out]"

        # 4. Construct the FFmpeg command
        command = [
            self.ffmpeg_path,
            "-y",
            "-framerate", str(fps),
            "-start_number", str(first_frame),
            "-i", ffmpeg_input_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-movflags", "+faststart",
        ]

        # -progress must come before the output path
        if on_ffmpeg_progress:
            command.extend(["-progress", "pipe:1"])

        command.append(ffmpeg_output_path)

        # Log command for debugging
        command_string = " ".join(str(c) for c in command)
        self.app.logger.debug("FFMPEG command:\n" + command_string)

        # Suppress the CMD window on Windows
        popen_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if sgtk.util.is_windows():
            popen_kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        # 5. Execute command
        process = subprocess.Popen(command, **popen_kwargs)

        if on_ffmpeg_progress:
            total_frames = int(settings["frame_range"][1]) - int(settings["frame_range"][0]) + 1

            # Drain stderr in background so the pipe never blocks
            stderr_lines = []
            def _drain_stderr():
                for raw in process.stderr:
                    stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip())
            drain_thread = threading.Thread(target=_drain_stderr, daemon=True)
            drain_thread.start()

            # Read structured progress from stdout line by line
            for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("frame="):
                    try:
                        on_ffmpeg_progress(int(line.split("=", 1)[1]), total_frames)
                    except ValueError:
                        pass

            process.wait()
            drain_thread.join()
            stderr_text = "\n".join(stderr_lines)
        else:
            _, stderr = process.communicate()
            stderr_text = stderr.decode("utf-8", errors="replace")

        self.app.logger.debug(stderr_text)

        if process.returncode != 0: raise Exception("FFMPEG encoding failed:\n" + stderr_text[-2000:])