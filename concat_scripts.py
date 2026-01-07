import logging
import os

# Configure logging per export-oriented standards
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_FILENAME = '_talos_concatenated_source.txt'
# Common directories to exclude to reduce noise and processing time
IGNORED_DIRS = {
    'venv', '.git', '__pycache__', '.idea', '.vscode', 'Binaries',
    'Intermediate'
}

# Extensions to include for context
INCLUDED_EXTENSIONS = ('.py', '.html', '.json', '.js', '.css', '.txt', '.md',
                       '.yaml', '.yml', '.toml')


def main():
    """Concatenates source files recursively, pruning specific directories."""
    cwd = os.getcwd()
    logger.info(f'Starting concatenation in: {cwd}')
    logger.info(f'Ignoring directories: {IGNORED_DIRS}')
    logger.info(f'Including extensions: {INCLUDED_EXTENSIONS}')

    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as outfile:
            file_count = 0

            for root, dirs, files in os.walk(cwd):
                # Modify dirs in-place to prevent os.walk from entering ignored directories
                # This is more efficient than checking paths inside the loop
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

                for file in files:
                    # Ignore this script itself and the output file to prevent recursion
                    if file.endswith(INCLUDED_EXTENSIONS) and file not in (
                            os.path.basename(__file__), OUTPUT_FILENAME):
                        file_path = os.path.join(root, file)

                        # Create a header for each file for readability
                        header = f'\n\n{"="*80}\nFILE: {file_path}\n{"="*80}\n\n'
                        outfile.write(header)

                        try:
                            with open(file_path, 'r',
                                      encoding='utf-8') as infile:
                                outfile.write(infile.read())
                            file_count += 1
                        except IOError as e:
                            logger.error(f'Could not read {file}: {e}')

        logger.info(
            f'Success. Concatenated {file_count} files into {OUTPUT_FILENAME}')

    except IOError as e:
        logger.error(f'Failed to write output file: {e}')


if __name__ == '__main__':
    main()
