import logging
import os

# Configure logging per export-oriented standards
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_FILENAME = '_hsh_concatenated_source.txt'


def main():
    """Concatenates all .py files in the tree into a single text file."""
    cwd = os.getcwd()
    logger.info(f'Starting concatenation in: {cwd}')

    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as outfile:
            file_count = 0
            
            for root, _, files in os.walk(cwd):
                for file in files:
                    if file.endswith('.py') and file != os.path.basename(__file__):
                        file_path = os.path.join(root, file)
                        
                        # Create a header for each file for readability
                        header = f'\n\n{"="*80}\nFILE: {file_path}\n{"="*80}\n\n'
                        outfile.write(header)
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as infile:
                                outfile.write(infile.read())
                            file_count += 1
                        except IOError as e:
                            logger.error(f'Could not read {file}: {e}')

        logger.info(f'Success. Concatenated {file_count} files into {OUTPUT_FILENAME}')

    except IOError as e:
        logger.error(f'Failed to write output file: {e}')


if __name__ == '__main__':
    main()