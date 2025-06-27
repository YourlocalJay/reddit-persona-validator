import PySimpleGUI as sg
from ..core.validator import RedditValidator
from pathlib import Path

sg.theme('DarkGrey5')

layout = [
    [sg.Text("Reddit Persona Validator", font=('Helvetica', 16))],
    [sg.HorizontalSeparator()],
    [sg.Text("Input File:"), sg.Input(key="-INFILE-", default_text="samples/input/test_accounts.txt"), sg.FileBrowse()],
    [sg.Text("Output Folder:"), sg.Input(key="-OUTFOLDER-", default_text="results"), sg.FolderBrowse()],
    [sg.Checkbox("Use AI Analysis", key="-USE_AI-", default=True)],
    [sg.Checkbox("Save Cookies", key="-SAVE_COOKIES-", default=True)],
    [sg.ProgressBar(100, orientation='h', size=(40, 20), key="-PROGRESS-")],
    [sg.Multiline(size=(60, 10), key="-LOG-", autoscroll=True, disabled=True)],
    [sg.Button("Run Validation"), sg.Button("Stop"), sg.Button("Open Output")]
]

window = sg.Window("Persona Validator", layout)

def run_validation(values):
    validator = RedditValidator(
        input_file=values["-INFILE-"],
        output_dir=values["-OUTFOLDER-"],
        use_ai=values["-USE_AI-"],
        save_cookies=values["-SAVE_COOKIES-"]
    )
    
    for progress, log in validator.execute():
        window["-PROGRESS-"].update(progress)
        window["-LOG-"].print(log)

while True:
    event, values = window.read(timeout=100)
    
    if event == sg.WIN_CLOSED:
        break
        
    if event == "Run Validation":
        run_validation(values)
        
    if event == "Open Output":
        output_file = Path(values["-OUTFOLDER-"]) / "report.csv"
        if output_file.exists():
            sg.execute(str(output_file))
