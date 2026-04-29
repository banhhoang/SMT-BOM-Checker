import streamlit as st
import pandas as pd
import io
import re

# 1. Định nghĩa từ khóa ở phạm vi toàn cục (Global) để chắc chắn không bị None
PN_KEYWORDS = ["P/N", "Part Number", "MPN"]
MFR_KEYWORDS = ["Hãng sản xuất", "Manufacturer", "Mfr"]

def super_clean(text):
    """Xóa tất cả ký tự đặc biệt và khoảng trắng để so sánh lõi"""
    if pd.isna(text): return ""
    clean_text = re.sub(r'[^a-zA-Z0-9]', '', str(text))
    return clean_text.lower()

def clean_column_names(df):
    """Làm sạch tiêu đề cột"""
    df.columns = [str(col).strip() for col in df.columns]
    return df

def get_all_values_from_row(row, keywords):
    """Lấy các giá trị P/N hoặc Hãng từ các cột tương ứng"""
    values = set()
    # Nếu keywords bị None (phòng hờ), gán thành danh sách rỗng
    search_keys = keywords if keywords is not None else []
    
    for col in row.index:
        col_str = str(col).lower()
        # Kiểm tra xem tên cột có chứa từ khóa không
        if any(key.lower() in col_str for key in search_keys):
            val = str(row[col]).strip()
            if val and val.lower() not in ['na', 'nan', 'none', '', '0']:
                values.add(val.upper())
    return values

def full_cross_check(df_bom, df_xy_combined):
    errors = []
    df_bom = clean_column_names(df_bom)
    df_xy_combined = clean_column_names(df_xy_combined)

    # Tìm các cột bắt buộc
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    
    col_xy_desig = next((c for c in df_xy_combined.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy_combined.columns if "Description" in c), None)
    
    if not all([col_bom_desc, col_bom_pos, col_bom_qty, col_xy_desig, col_xy_desc]):
        return "Lỗi: Không tìm thấy đủ các cột cần thiết (Mô tả, Vị trí, Số lượng, Designator, Description). Hãy kiểm tra lại tên cột trong file Excel."

    all_bom_positions = {}

    # --- CHIỀU 1: TỪ BOM SANG XY DATA ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[col_bom_pos])
        if pd.isna(row[col_bom_pos]) or pos_raw.strip() == "" or "Tích hợp" in pos_raw:
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        try:
            bom_qty = int(float(row[col_bom_qty])) # Xử lý nếu số lượng là dạng 1.0
        except:
            bom_qty = 0
            
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        # Thu thập P/N và Hãng từ BOM
        bom_pns = get_all_values_from_row(row, PN_KEYWORDS)
        bom_mfrs = get_all_values_from_row(row, MFR_KEYWORDS)
        
        for p in pos_list:
            all_bom_positions[p] = {"desc": bom_desc, "pns": bom_pns, "mfrs": bom_mfrs}

        if len(pos_list) != bom_qty:
            errors.append({"Vị trí": pos_raw, "Loại lỗi": "Sai SL BOM", "Chi tiết": f"Ghi {bom_qty} nhưng đếm {len(pos_list)}", "Nguồn lỗi": "BOM"})

    # --- SO KHỚP TỪNG VỊ TRÍ ---
    for pos, info in all_bom_positions.items():
        match_xy = df_xy_combined[df_xy_combined[col_xy_desig] == pos]
        if match_xy.empty:
            errors.append({"Vị trí": pos, "Loại lỗi": "Thiếu tọa độ", "Chi tiết": "Có trong BOM nhưng không có trong XY", "Nguồn lỗi": "Tổng XY"})
        else:
            xy_row = match_xy.iloc[0]
            current_errors = []
            
            # 1. Check Mô tả
            if super_clean(info['desc']) != super_clean(xy_row[col_xy_desc]):
                current_errors.append(f"[Mô tả] BOM: '{info['desc']}' vs XY: '{xy_row[col_xy_desc]}'")
            
            # 2. Check P/N
            xy_pns = get_all_values_from_row(xy_row, PN_KEYWORDS)
            if info['pns'] and xy_pns and not (info['pns'] & xy_pns):
                current_errors.append(f"[P/N] BOM: {info['pns']} vs XY: {xy_pns}")
            
            # 3. Check Hãng
            xy_mfrs = get_all_values_from_row(xy_row, MFR_KEYWORDS)
            if info['mfrs'] and xy_mfrs and not (info['mfrs'] & xy_mfrs):
                current_errors.append(f"[Hãng] BOM: {info['mfrs']} vs XY: {xy_mfrs}")

            if current_errors:
                errors.append({"Vị trí": pos, "Loại lỗi": "Sai thông tin", "Chi tiết": " | ".join(current_errors), "Nguồn lỗi": xy_row.get("File Nguồn", "XY Data")})

    # --- CHIỀU 2: TỪ XY DATA SANG BOM ---
    for _, row in df_xy_combined.iterrows():
        xy_pos = str(row[col_xy_desig]).strip()
        if xy_pos not in all_bom_positions:
            errors.append({"Vị trí": xy_pos, "Loại lỗi": "Thừa trong XY Data", "Chi tiết": "Vị trí có tọa độ nhưng không có trong BOM", "Nguồn lỗi": row.get("File Nguồn", "XY Data")})

    return pd.DataFrame(errors)

# --- GIAO DIỆN ---
st.set_page_config(page_title="SMT Checker Fixed", layout="wide")
st.title("Đối soát BOM & XY Data (Bản sửa lỗi NoneType)")

f_bom = st.file_uploader("1. Upload BOM", type=['xlsx', 'csv'])
f_xys = st.file_uploader("2. Upload XY DATA", type=['xlsx', 'csv'], accept_multiple_files=True)

if f_bom and f_xys:
    try:
        df_bom = pd.read_excel(f_bom) if f_bom.name.endswith('.xlsx') else pd.read_csv(f_bom)
        list_xy = []
        for f in f_xys:
            t = pd.read_excel(f) if f.name.endswith('.xlsx') else pd.read_csv(f)
            t["File Nguồn"] = f.name
            list_xy.append(t)
        df_combined = pd.concat(list_xy, ignore_index=True)
        
        if st.button("🚀 Chạy đối soát"):
            res = full_cross_check(df_bom, df_combined)
            if isinstance(res, str):
                st.error(res)
            elif res.empty:
                st.success("✅ Khớp 100%!")
            else:
                st.warning(f"Phát hiện {len(res)} lỗi.")
                st.dataframe(res, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
                    res.to_excel(wr, index=False)
                st.download_button("Tải báo cáo lỗi", out.getvalue(), "Bao_cao_SMT_Fixed.xlsx")
    except Exception as e:
        st.error(f"Lỗi đọc file: {e}")
