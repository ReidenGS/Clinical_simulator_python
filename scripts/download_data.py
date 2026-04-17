"""
Download required datasets for clinical_simulator_dev.
Run once after cloning the repository:

    python scripts/download_data.py
"""

from datasets import load_dataset
import os

SAVE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "open_patients")

def main():
    print("Downloading ncbi/Open-Patients from HuggingFace...")
    dataset = load_dataset("ncbi/Open-Patients", split="train")
    save_path = os.path.abspath(SAVE_PATH)
    os.makedirs(save_path, exist_ok=True)
    dataset.save_to_disk(save_path)
    print(f"Done. Dataset saved to: {save_path}")
    print(f"Total examples: {len(dataset)}")

if __name__ == "__main__":
    main()
