from config.config_loader import load_keywords


def main():
    keywords = load_keywords()

    for keyword in keywords:
        print(f"Searching: {keyword}")

if __name__ == "__main__":
    main()
        # Add your processing logic here