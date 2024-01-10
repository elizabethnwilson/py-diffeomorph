import PySimpleGUI as sg
import diffeomorphic as diffeo
import pathlib as pl
import functools
from inspect import unwrap
from math import floor
from time import sleep


class ProgressUpdater:
    """
    Dynamically updates progress bar's status based on number of files. Adds
    specified stage_progress value in __init__() to update bar's current progress.

    stage_progress can be thought of as the percent of the bar (assuming max value is 100)
    which should be completed overall by the wrapped function. Combine with runs_each_file
    to have progress increment proportionally based on completion of each file (default behavior).

    Since each run of a wrapped function running on multiple files will increment, the final value
    will not always be the max value due to rounding. When complete, the bar's value should manually
    be updated to max.
    """

    # Global for the entire GUI
    current_progress: int = 0

    @staticmethod
    def reset():
        """
        Should be called during cleanup for future runs in the event loop.
        """
        ProgressUpdater.current_progress = 0

    def __init__(
        self,
        func,
        pbar_key: str,
        label_key: str,
        window: sg.Window,
        stage_progress: int,
        num_files: int,
        label: str,
        runs_each_file: bool = True,
    ):
        functools.update_wrapper(self, func)
        self.func = func
        self.pbar_key: str = pbar_key
        self.label_key: str = label_key
        self.window: sg.Window = window
        self.label = label

        if not runs_each_file:
            self.increment_value: int = stage_progress
            self.runs_each_file = False
            return

        self.runs_each_file = True
        # Calculate amount to increment when wrapped function is called based on number of files
        self.file_count: int = 1
        self.increment_value: int = floor(stage_progress / num_files)

    def __call__(self, *args, **kwargs):
        """
        WARNING: wrapped functions may raise FileNotFoundError.
        """

        # When using, try to avoid letting this exceed pbar's max
        ProgressUpdater.current_progress += self.increment_value
        self.window[self.pbar_key].update(
            current_count=ProgressUpdater.current_progress
        )

        if self.runs_each_file:
            # Since file count is an attribute of each object rather than the class,
            # only use it when it is set to avoid an AttributeError
            extended_label: str = f"File #{self.file_count}: {self.label}"
            self.file_count += 1
        else:
            extended_label: str = self.label

        self.window[self.label_key].update(value=extended_label)

        # This updates the window since we are operating within one iteration of event loop.
        self.window.refresh()

        print(*args, **kwargs)

        return self.func(*args, **kwargs)

    def __get__(self, instance, owner):
        return functools.partial(self.__call__, instance)


sg.theme("SystemDefault")

layout = [
    [sg.T("")],
    [
        sg.Text("Select files to diffeomorph: "),
        sg.Input(key="-INPUTS-"),
        sg.FilesBrowse(),
    ],
    [sg.T("")],
    [
        sg.Text("Select an output folder: "),
        sg.Input(key="-OUTPUT-"),
        sg.FolderBrowse(),
    ],
    [sg.T("")],
    [
        sg.Text("Set maxdistortion (default is 80): "),
        sg.Input(default_text="80", key="-MAXDISTORTION-", enable_events=True),
    ],
    [
        sg.Text("Set nsteps (default is 20): "),
        sg.Input(default_text="20", key="-NSTEPS-", enable_events=True),
    ],
    [sg.Checkbox("Save each step? ", key="-SAVE_STEPS-")],
    [sg.Checkbox("Disable upscaling?", key="-NO_UPSCALING-")],
    [sg.Text("", key="-PBARLABEL-", visible=False)],
    [
        sg.ProgressBar(
            100, orientation="horizontal", key="-PBAR-", style="classic", visible=False
        )
    ],
    [sg.Text("", key="-ERROR-")],
    [sg.Button("Run")],
]

window = sg.Window("PyDiffeomorph", layout)

while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break

    # Only allow digits in maxdistortion and nsteps input fields
    if event == "-MAXDISTORTION-":
        if values["-MAXDISTORTION-"][-1] not in ("0123456789"):
            window["-MAXDISTORTION-"].update(values["-MAXDISTORTION-"][:-1])
    if event == "-NSTEPS-":
        if values["-NSTEPS-"][-1] not in ("0123456789"):
            window["-NSTEPS-"].update(values["-NSTEPS-"][:-1])

    if event == "Run":
        # Debug
        print(values)
        # Check that files/folders are supplied for program to run
        if not values["-INPUTS-"] and not values["-OUTPUT-"]:
            window["-ERROR-"].update(
                value="ERROR: One or more files/folders must be supplied as an input; exactly one folder must be supplied as an output",
                text_color="red",
            )
            # Skips diffeo when missing values
            continue
        elif not values["-INPUTS-"]:
            window["-ERROR-"].update(
                value="ERROR: One or more files/folders must be supplied as an input",
                text_color="red",
            )
            continue
        elif not values["-OUTPUT-"]:
            window["-ERROR-"].update(
                value="ERROR: Exactly one folder must be supplied as an output",
                text_color="red",
            )
            continue

        # Clear error
        window["-ERROR-"].update(value="")

        window["-PBAR-"].update(current_count=0, visible=True)
        window["-PBARLABEL-"].update(visible=True)

        inputs: list = [pl.Path(file) for file in values["-INPUTS-"].split(";")]
        output_dir: pl.Path = pl.Path(values["-OUTPUT-"])
        maxdistortion: int = int(values["-MAXDISTORTION-"])
        nsteps: int = int(values["-NSTEPS-"])
        save_steps: bool = values["-SAVE_STEPS-"]
        upscale: bool = not values["-NO_UPSCALING-"]

        num_files: int = len(inputs)

        # Wrap functions that should update progress bar when run
        diffeo.DiffeoImage.__init__ = ProgressUpdater(
            diffeo.DiffeoImage.__init__,
            "-PBAR-",
            "-PBARLABEL-",
            window,
            5,
            num_files,
            "Initializing image...",
        )
        diffeo.DiffeoImage._getdiffeo = ProgressUpdater(
            diffeo.DiffeoImage._getdiffeo,
            "-PBAR-",
            "-PBARLABEL-",
            window,
            25,
            num_files,
            "Generating diffeomorphic flow field...",
        )
        diffeo.DiffeoImage._interpolate_image = ProgressUpdater(
            diffeo.DiffeoImage._interpolate_image,
            "-PBAR-",
            "-PBARLABEL-",
            window,
            65,
            num_files,
            "Interpolating image (this may take a while; do not close window!)...",
        )
        diffeo.DiffeoImageDir.save = ProgressUpdater(
            diffeo.DiffeoImageDir.save,
            "-PBAR-",
            "-PBARLABEL-",
            window,
            5,
            num_files,
            "Saving files (do not close window!)...",
            runs_each_file=False,
        )

        try:
            print(inputs, output_dir, maxdistortion, nsteps, save_steps, upscale)
            # Somehow, the output dir's type is int in DiffeoImageDir's init function on second run - fix
            diffeo.run_diffeomorph(
                inputs,
                output_dir,
                maxdistortion,
                nsteps,
                save_steps,
                upscale,
            )
        except FileNotFoundError:
            window["-INPUTS-"].update(value="")
            window["-OUTPUTS-"].update(value="")
            window["-ERROR-"].update(value="ERROR: One or more files not found")
        else:
            window["-PBAR-"].update(current_count=100)
            window["-PBARLABEL-"].update(value="Diffeomorphing complete!")
            window.refresh()
            sleep(2)
        finally:
            # Cleanup for next run

            window["-PBAR-"].update(current_count=0, visible=False)
            window["-PBARLABEL-"].update(value="", visible=False)

            # Unwrap functions for next iteration of loop since values can change
            # and to avoid wrapping a wrapped function again
            diffeo.DiffeoImage.__init__ = unwrap(diffeo.DiffeoImageDir.__init__)
            diffeo.DiffeoImage._getdiffeo = unwrap(diffeo.DiffeoImage._getdiffeo)
            diffeo.DiffeoImage._interpolate_image = unwrap(
                diffeo.DiffeoImage._interpolate_image
            )
            diffeo.DiffeoImageDir.save = unwrap(diffeo.DiffeoImageDir.save)

            ProgressUpdater.reset()
