# Updated CLI arguments
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", nargs="+", required=True)
    parser.add_argument("--prompt", help="Path to custom prompt file")
    parser.add_argument("--with_keywords", action="store_true")
    parser.add_argument("--keyword_model", default="gpt-4o-mini")

    # New argument to control parsing mode
    parser.add_argument(
        "--mode",
        choices=["datasheet", "generic", "auto"],
        default="auto",
        help="Parsing mode: 'datasheet' for pair extraction, 'generic' for simple PDF, 'auto' to detect",
    )

    parser.add_argument("--config", default="config.yaml", help="Config file")

    args = parser.parse_args()

    # Determine parsing behavior
    if args.mode == "auto":
        # Auto-detect based on prompt content or filename patterns
        is_datasheet_mode = "datasheet" in (args.prompt or "").lower()
    else:
        is_datasheet_mode = args.mode == "datasheet"
