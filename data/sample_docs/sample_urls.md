# Sample URLs for Pipeline v3 Testing

This file contains tested URLs that can be used with Pipeline v3's URL batch processing feature.

## Test URLs

1. [PowerMax-USB UV/VIS Power Sensors Datasheet](https://www.coherent.com/content/dam/coherent/site/en/resources/datasheet/power-and-energy-measurement/powermax-usb-uv-vis-power-sensors-ds.pdf)
2. [Understanding a Certificate of Calibration](https://www.coherent.com/content/dam/coherent/site/en/resources/laser-measurement-and-control-help-center/application-notes-and-white-papers/application-notes/understanding-a-certificate-of-calibration.pdf)

## Usage

Process these URLs using the batch processing feature:

```bash
# Process URLs from this file
uv run python -m src.pipeline_v3.cli_main add dummy --url-file data/sample_docs/sample_urls.md --with-keywords --mode auto
```