# P3CC (P3 Collect-Comparative)

## Overview

P3CC is a Python-based utility designed to process `.p3` files and enrich them with data from Excel spreadsheets. It automates the collection and comparison of card-related information, integrating details like cardholder names, national IDs, mobile numbers, and other profile-specific data directly into the `.p3` output files.

The program is structured into three main Python files:
- `main.py`: The entry point of the application, orchestrating the file selection, data processing, and output generation.
- `utils.py`: Contains pure helper functions for data transformation, file handling, profile detection, and text building. It's designed for reusability and testability.
- `config.py`: Centralizes all configurable parameters, such as encoding, file extensions, binary markers, profile signatures, and field mappings. This file is designed to be easily modified without touching the core logic.
- `exceptions.py`: Defines custom exception classes for specific error conditions within the application, allowing for more precise error handling and clearer debugging.

## Features

- **Profile-based Processing**: Automatically detects the Excel file structure (e.g., 'Yalla', 'Zamalek', 'Classic') and applies the correct data mapping.
- **Efficient Data Lookup**: Uses Pandas DataFrames with indexed lookups for fast retrieval of card data.
- **Arabic Character Normalization**: Includes robust handling for Arabic characters and numbers.
- **Configurable Field Mapping**: Easily extendable to support new Excel columns or output tags via `config.py`.
- **Progress Tracking**: Provides a progress bar for long-running operations.
- **Logging**: Detailed logging for better traceability and debugging.

## How to Use

1.  **Prerequisites**:
    *   Ensure you have Python 3.x installed.
    *   Install the required libraries by running:
        ```bash
        pip install -r requirements.txt
        ```

2.  **Prepare Your Files**:
    *   Place your `.p3` source files in a designated folder.
    *   Have your Excel spreadsheet (`.xlsx` or `.xls`) ready with the data you want to integrate.

3.  **Launch the Program**:
    *   Navigate to the project directory in your terminal.
    *   Run the `run.bat` file:
        ```bash
        run.bat
        ```
    *   Alternatively, you can run `main.py` directly:
        ```bash
        python main.py
        ```

4.  **Follow the Prompts**:
    *   The program will first ask you to select the folder containing your `.p3` files.
    *   Next, it will prompt you to select your Excel data file.
    *   P3CC will then process the files, displaying a progress bar.
    *   Upon completion, it will generate a new `.p3` output file in the same directory as your source `.p3` files, named after the source folder (e.g., `My P3 Files.p3` becomes `My_P3_Files.p3`).

## Configuration (`config.py`)

The `config.py` file is the central place for all program settings. You can modify it to adapt P3CC to different data structures or output requirements.

### Key Sections to Modify:

#### 1. `ENCODING`
- **Purpose**: Specifies the character encoding for reading and writing `.p3` files.
- **Example**: `ENCODING = 'cp1256'` (Common for Arabic Windows environments)

#### 2. `CARD_FILE_EXT`
- **Purpose**: Defines the file extension for the card data files.
- **Example**: `CARD_FILE_EXT = 'p3'`

#### 3. `PROFILE_SIGNATURES`
- **Purpose**: Maps profile names to a dictionary containing:
    *   `'signatures'`: A list of column names that *must* exist in the Excel file for that profile to be detected.
    *   `'lookup_col'`: The column name to use for indexing the Excel DataFrame (e.g., 'Card No').
- The order of profiles in this dictionary matters; the first matching profile will be selected.
- **How to Add/Modify**:
    *   To add a new profile, add a new entry to this dictionary.
    *   The key is your chosen profile name (e.g., `'my_new_profile'`).
    *   The value is a dictionary specifying its `signatures` and `lookup_col`.
- **Example**:
```python
PROFILE_SIGNATURES = {
    'classic': {
        'signatures': ['Card No'],
        'lookup_col': 'Card No',
    },
    'yalla': {
        'signatures': ['Mobile Number'],
        'lookup_col': 'Card No',
    },
    'zamalek': {
        'signatures': ['رقم بطاقة الصراف الالى'],
        'lookup_col': 'رقم بطاقة الصراف الالى',
    },
    'my_new_profile': {
        'signatures': ['Unique Column A', 'Unique Column B'],
        'lookup_col': 'Unique Column A',
    },
}
```

#### 4. `FIELD_MAP`
- **Purpose**: Defines how data from your Excel file is mapped to the output `.p3` file for each detected profile. Each entry is a tuple: `(output_tag, col_def, processor_key)`.
- **How to Add/Modify**:
    *   **`output_tag` (string)**: The tag that will be written to the `.p3` file (e.g., `'<arabic>'`, `'<MobileNumber>'`).
    *   **`col_def` (string, list of strings, `None`, or `'__line_count__'`)**:
        *   **String**: A direct column name from your Excel sheet (e.g., `'CardHolder Name'`).
        *   **List of Strings**: A list of fallback column names. The program will try each name in order, using the first one it finds (e.g., `['الاسم', 'الإســــــم']`).
        *   **`None`**: Indicates that no specific column value is used; the tag will be written with an empty value (e.g., for `<address>` if the address is not in Excel).
        *   **`'__line_count__'`**: A special sentinel that injects the current card counter (line number) into the output. Used for dynamic values not present in Excel.
    *   **`processor_key` (string or `None`)**:
        *   A string key that refers to a data processing function defined in `utils.py`'s `_PROCESSOR_REGISTRY`.
        *   Common keys include:
            *   `'col_check'`: Applies `col_check` (handles NaN/None values, strips whitespace).
            *   `'chr_replace'`: Applies `chr_replace` (normalizes Arabic characters).
            *   `'jpg'`: Appends `.JPG` to the value.
        *   **`None`**: If `None`, the value is simply converted to a string without any special processing.

- **Example (Adding a new field to an existing profile)**:
    Let's say you want to add a new field `<Email>` to the `yalla` profile, and its column in Excel is `Email Address`.
```python
FIELD_MAP = {
    'yalla': [
        # ... existing fields ...
        ('<address>',       'Address',                      None),
        ('<city>',          'City',                         None),
        ('<Email>',         'Email Address',                None), # New field
    ],
    # ... other profiles ...
}
```

- **Example (Adding a new profile)**:
    If you added `'my_new_profile'` to `PROFILE_SIGNATURES`, you would then define its field map:
```python
FIELD_MAP = {
    # ... existing profiles ...
    'my_new_profile': [
        ('<ID>',            'Unique Column A',              None),
        ('<Name>',          'Customer Name',                'chr_replace'),
        ('<Status>',        'Account Status',               'col_check'),
        ('<Counter>',       '__line_count__',               None),
    ],
}
```

## Error Handling (`exceptions.py`)

The `exceptions.py` file defines custom exception classes that are used throughout the P3CC application for specific error conditions. This allows for more precise error handling and provides clearer, more descriptive error messages, which aids in debugging and troubleshooting.

-   **`P3CCError`**: The base exception for all custom errors in P3CC. All other custom exceptions inherit from this.
-   **`ProfileDetectionError`**: Raised when the program cannot identify a matching profile for the provided Excel file based on the `PROFILE_SIGNATURES` in `config.py`.
-   **`SourceFilesError`**: Raised when no `.p3` source files are found in the selected directory.
-   **`MissingColumnError`**: Raised when a required column (as defined in `FIELD_MAP` or `PROFILE_SIGNATURES`) is missing from the Excel data.
-   **`InvalidCardError`**: Raised when card data is found to be malformed or does not meet expected criteria during processing.

## Project Structure

```
P3ccV2/
├── main.py             # Main application logic and execution flow
├── utils.py            # Helper functions for data processing, file operations, etc.
├── config.py           # Centralized configuration for profiles, field mappings, and constants
├── exceptions.py       # Custom exception definitions for robust error handling
├── requirements.txt    # List of Python dependencies
├── run.bat             # Batch file to easily launch the program
└── README.md           # This documentation
```
