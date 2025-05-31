DATASHEET_PARSE_PROMPT = """# CRITICAL PARSING INSTRUCTIONS - FOLLOW EXACTLY

These documents contain technical information about laser power meters, laser energy meters, and laser beam diagnostics products.

When you are parsing a technical product datasheet, always:
1. Follow table formatting rules
2. Extract pairs of model names and part numbers

## TABLE FORMATTING RULES:

1. FILL ALL EMPTY CELLS: Every cell in specification tables must be filled. No cell should be empty.
   - When a value spans multiple columns, copy that value to each individual cell it applies to.
   - Example: If "0.19 to 12" appears once but applies to all models, it must be repeated in each model's column.

2. TABLE STRUCTURE: Include model names in the first row of each column above specifications.
   - Example: |Model|PM2|PM10|PM30|

3. PART NUMBERS:
   - Keep part numbers within specification tables
   - Remove any footnote symbols/superscripts from part numbers
   - Most part numbers have seven digits unless they start with 33 and include dashes

## EXAMPLES OF CORRECT TABLE FORMATTING:

INCORRECT (with empty cells):
|Wavelength Range (µm)| |0.19 to 12| | |
|Active Area Diameter (mm)|50| |25|10|

CORRECT (all cells filled):
|Wavelength Range (µm)|0.19 to 12|0.19 to 12|0.19 to 12|0.19 to 12|
|Active Area Diameter (mm)|50|50|25|10|

## PAIR EXTRACTION RULES:

4.  **CABLE TYPE HANDLING (CRITICAL):**
    *   Many sensor part numbers specify a cable type (e.g., `(USB)`, `(RS)`, `DB25`) immediately following the number within the same table cell or within the lower part of the specification table.
    *   When extracting pairs, **APPEND the cable type** to the model name if present.
    *   Use the format: `[Model Name] [Cable Type]` (e.g., "PM10 USB", "PM30 RS-232", "J-10MB-LE DB25").
    *   Common cable types to look for: USB, RS (treat as RS-232), DB25. Use the abbreviation found in the table cell (e.g., use "RS" if the table says "(RS)").
    *   If a single cell under a model column contains multiple part numbers with different cable types, create a **separate pair for each one**.
    *   If no cable type is explicitly mentioned next to the part number in its cell, especially when you determine the product to be some type other than sensor, **DO NOT** append anything to the model name.

## EXAMPLES OF CORRECT PAIR EXTRACTION (incorporating cable types):

Consider this table cell under the 'PM30' column: `1174257 (USB)² \\n 1174258 (RS)`

CORRECT PAIRS EXTRACTED:
('PM30 USB', '1174257')
('PM30 RS', '1174258')

Consider this cell under the 'PM10' column: `1174262 (USB)²`

CORRECT PAIR EXTRACTED:
('PM10 USB', '1174262')

Consider this cell under the 'PM2' column: `1174264` (no cable type mentioned)

CORRECT PAIR EXTRACTED:
('PM2', '1174264')


## FINAL OUTPUT FORMAT within the text:

Ensure the final output in the text strictly follows this format if pairs are found:

Metadata: {
    'pairs': [
        ('Sensor Model Name with Cable Type', 'PartNumber'),
        ('Another Sensor Model with Cable Type', 'AnotherPartNumber'),
        ('Meter Model Name', 'MeterPartNumber')
    ]
}
"""
