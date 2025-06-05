import streamlit as st
import cv2
import pytesseract
import numpy as np
import pandas as pd
from pdf2image import convert_from_path
import tempfile
import os

st.set_page_config(page_title="BOE PDF OCR App", layout="wide")
st.title("📄 BOE PDF OCR & Accuracy Checker")

# Region defaults (you can adjust these interactively if needed)
DEFAULT_REGIONS = [
    (986, 407, 1913, 723),    # Description 1
    (146, 772, 1219, 1069),   # Amount 1
    (1014, 1148, 1919, 1520), # Description 2
    (155, 1556, 1218, 1817),  # Amount 2
    (991, 1893, 1928, 2262),  # Description 3
    (153, 2269, 1216, 2537)   # Amount 3
]

def is_number(s):
    try:
        float(s.replace(",", ""))
        return True
    except:
        return False

def extract_description(text_lines):
    for i, line in enumerate(text_lines):
        if "ITEM DESCRIPTION" in line.upper():
            return text_lines[i + 1].strip() if i + 1 < len(text_lines) else "[Description Not Found]"
    return "[ITEM DESCRIPTION not detected]"

def extract_last_two_amounts(text_lines):
    numbers = [line for line in text_lines if is_number(line)]
    return numbers[-2:] if len(numbers) >= 2 else ["[Not Found]"]

uploaded_pdf = st.file_uploader("Upload BOE PDF file", type=["pdf"])
first_page = st.number_input("First page (1-indexed):", min_value=1, value=6)
last_page = st.number_input("Last page (inclusive):", min_value=first_page, value=8)
wire_tolerance = st.number_input("SWS Tolerance Value:", min_value=0.01, value=0.1, step=0.01)

if uploaded_pdf is not None:
    if st.button("Start OCR & Analysis"):
        with tempfile.TemporaryDirectory() as tmpdirname:
            pdf_path = os.path.join(tmpdirname, uploaded_pdf.name)
            with open(pdf_path, "wb") as f:
                f.write(uploaded_pdf.read())
            
            with st.spinner("Converting PDF pages to images..."):
                pages = convert_from_path(pdf_path, first_page=first_page, last_page=last_page, dpi=300)
            
            ocr_data = []
            with st.spinner("Extracting data from pages..."):
                for page_idx, page_image in enumerate(pages, start=first_page):
                    img = np.array(page_image)[:, :, ::-1]  # RGB to BGR
                    for i in range(0, len(DEFAULT_REGIONS), 2):
                        # Description
                        x1, y1, x2, y2 = DEFAULT_REGIONS[i]
                        desc_crop = img[y1:y2, x1:x2]
                        desc_crop = cv2.cvtColor(desc_crop, cv2.COLOR_GRAY2BGR) if len(desc_crop.shape) == 2 else desc_crop
                        desc_text = pytesseract.image_to_string(desc_crop, config='--oem 3 --psm 12')
                        desc_lines = [line.strip() for line in desc_text.split("\n") if line.strip()]
                        desc = extract_description(desc_lines)
                        
                        # Amount
                        x1, y1, x2, y2 = DEFAULT_REGIONS[i + 1]
                        amount_crop = img[y1:y2, x1:x2]
                        amount_crop = cv2.cvtColor(amount_crop, cv2.COLOR_GRAY2BGR) if len(amount_crop.shape) == 2 else amount_crop
                        amount_text = pytesseract.image_to_string(amount_crop, config='--oem 3 --psm 12')
                        amount_lines = [line.strip() for line in amount_text.split("\n") if line.strip()]
                        amounts = extract_last_two_amounts(amount_lines)
                        
                        if "[Description" in desc or not any(is_number(a) for a in amounts):
                            continue
                        
                        try:
                            ocr_data.append({
                                "Page": page_idx,
                                "Block": f"Region {i//2 + 1}",
                                "Model Name": desc,
                                "BCD Amount": float(amounts[0].replace(",", "")) if is_number(amounts[0]) else None,
                                "SWS Amount": float(amounts[1].replace(",", "")) if len(amounts) > 1 and is_number(amounts[1]) else None
                            })
                        except Exception as e:
                            st.warning(f"⚠️ Error processing amounts on Page {page_idx}, Region {i//2 + 1}: {e}")

            if not ocr_data:
                st.error("No valid data found! Please check region coordinates and PDF pages.")
            else:
                df = pd.DataFrame(ocr_data)
                df["Expected_SWS"] = df["BCD Amount"] * 0.10
                df["Difference"] = abs(df["SWS Amount"] - df["Expected_SWS"])
                df["Is_Accurate"] = df["Difference"] <= wire_tolerance

                total = len(df)
                correct = df["Is_Accurate"].sum()
                accuracy = (correct / total) * 100 if total > 0 else 0

                st.success(f"✅ Total rows checked: {total}")
                st.success(f"✅ Correct SWS values: {correct}")
                st.info(f"📊 Accuracy: {accuracy:.2f}%")

                st.dataframe(df)
                incorrect_df = df[~df["Is_Accurate"]]
                if not incorrect_df.empty:
                    st.warning("❌ Incorrect SWS rows:")
                    st.dataframe(incorrect_df[["Page", "Block", "Model Name", "BCD Amount", "SWS Amount", "Expected_SWS"]])
                
                # Download buttons
                st.download_button(
                    "Download All Results (Excel)",
                    data=df.to_excel(index=False, engine='openpyxl'),
                    file_name="BOE_ALL_with_accuracy.xlsx"
                )
                if not incorrect_df.empty:
                    st.download_button(
                        "Download Incorrect Only (Excel)",
                        data=incorrect_df.to_excel(index=False, engine='openpyxl'),
                        file_name="BOE_ONLY_incorrect.xlsx"
                    )
    else:
        st.info("⬆️ Upload a file and click **Start OCR & Analysis** to begin.")

