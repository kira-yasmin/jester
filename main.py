import argparse as ap
import logging

from os.path import isdir, isfile, abspath, join, basename
from sys import exit

from PyQt5.QtWidgets import QApplication

from jester.classifier import CandClassifier as CandClass

logger = logging.getLogger()

def main():

    parser = ap.ArgumentParser(description="Classifier for MeerTRAP",
                               usage="%(prog)s <options>")

    parser.add_argument("-d", "--directory", help="Input data directory",
                        required=True,
                        type=str)
    parser.add_argument("-e", "--extension", help="Plot extension",
                        required=False,
                        type=str,
                        default="png")
    parser.add_argument("-o", "--output", help="Output file name (written inside -d directory, used if -c is not specified)",
                        required=False,
                        type=str,
                        default="results.csv")
    parser.add_argument("-c", "--csv", help="Full path to the CSV output file (overrides -o, allows sharing one CSV across timescales)",
                        required=False,
                        type=str,
                        default=None)
    parser.add_argument("-t", "--timescale", help="Timescale being classified (e.g. 1s, 10s, 30s). "
                        "If not specified, inferred from the last _-separated part of the parent directory name.",
                        required=False,
                        type=str,
                        default=None)

    arguments = parser.parse_args()

    if not isdir(arguments.directory):
        logger.error(f"Directory {arguments.directory} does not exist!")
        exit()

    # Infer timescale from parent directory name if not specified
    if arguments.timescale:
        timescale = arguments.timescale
    else:
        # e.g. .../cutouts_1572120061_LMC1R12C08_8s/eta_V_high -> parent is cutouts_..._8s -> last part is 8s
        parent_dir = basename(abspath(join(arguments.directory, "..")))
        timescale = parent_dir.split("_")[-1]
        logger.info(f"No timescale specified, inferred '{timescale}' from directory name '{parent_dir}'")

    # If -c is given, use it as the full CSV path; otherwise fall back to -o inside the directory
    if arguments.csv:
        csv_path = abspath(arguments.csv)
        # If the user passed a directory instead of a file, append the default filename
        if isdir(csv_path):
            csv_path = join(csv_path, arguments.output)
    else:
        csv_path = abspath(join(arguments.directory, arguments.output))

    app = QApplication([])
    cc = CandClass(arguments.directory, csv_path, arguments.extension, timescale)

    try:
        app.exec()
    except Exception as exc:
        logger.error(exc)

if __name__ == "__main__":
    main()