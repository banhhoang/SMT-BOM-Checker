import streamlit as st
import pandas as pd
import io
import re

# 1. Hàm làm sạch chuỗi (Xóa ký tự đặc biệt để so sánh lõi)
def super_clean(text):
    if pd.isna(text): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

# 2. Hàm tìm cột thông minh
def find_column(df, keywords):
    for col in df.columns:
        col_clean = super_clean(col)
        for k in keywords:
            if super_clean(k) in col_clean:
                return col
    return None

# 3. Hàm lấy dữ liệu (Đã sửa logic để không nhầm PN với Hãng)
def get_values(row, keywords, exclude_keywords=None):
    vals = set()
    for col in row.index:
        col_str = str(col).lower()
        # Kiểm tra từ khóa chính
        if any(k.lower() in col_str for k in keywords):
            # Kiểm tra từ khóa loại trừ (ví dụ: tránh "Manufacturer Part Number" khi tìm Hãng)
            if exclude_keywords and any(ex.lower() in col_str for ex in exclude_keywords):
                continue
            
            v = str(row[col]).strip()
            if v and v.lower() not in ['nan', 'na', 'none', '0', '']:
                vals.add(v.upper())
    return vals

def full_cross_check(df_bom, df_xy):
    errors = []
    
    # Định vị các cột quan trọng
    c_bom_desc = find_column(df_bom, ["Mô tả", "Description", "Yêu cầu kỹ thuật"])
    c_bom_pos = find_column(df_bom, ["Vị trí", "Designator", "VTLK"])
    c_bom_qty = find_column(df_bom, ["Số lượng", "Qty"])
    
    c_xy_desig = find_column(df_xy, ["Designator", "Vị trí"])
    c_xy_desc = find_column(df_xy, ["Description", "Mô tả"])

    if not all([c_bom_desc, c_bom_pos, c_bom_qty, c_xy_desig, c_xy_desc]):
        return "Lỗi: App không tìm thấy đủ cột cần thiết. Hãy kiểm tra tiêu đề file."

    all_bom_pos = {}

    # --- DUYỆT FILE BOM ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[c_bom_pos])
        if pd.isna(row[c_bom_pos]) or not pos_raw.strip() or "Tích hợp" in pos_raw:
            continue

        desc = str(row[c_bom_desc]).strip()
        try:
            qty = int(float(row[c_bom_qty]))
        except: qty = 0
            
        # P/N Keywords: P/N, Part Number
        pns = get_values(row, ["P/N", "Part Number"])
        # Hãng Keywords: Hãng, Manufacturer (nhưng loại trừ nếu có chữ PN/Part Number)
        mfrs = get_values(row, ["Hãng", "Manufacturer"], exclude_keywords=["Part Number", "P/N", "PN"])
        
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        for p in pos_list:
            all_bom_pos[p] = {"desc": desc, "pns": pns, "mfrs": mfrs}

        if len(pos_list) != qty:
            errors.append({
                "Vị trí": pos_raw, "Loại lỗi": "Sai SL BOM",
                "Chi tiết": f"Ghi {qty} nhưng liệt kê {len(pos_list)}", "Nguồn": "BOM"
            })

    # --- SO KHỚP VỚI XY DATA ---
    for pos, info in all_bom_pos.items():
        match = df_xy[df_xy[c_xy_desig] == pos]
        if match.empty:
            errors.append({"Vị trí": pos, "Loại lỗi": "Thiếu tọa độ", "Chi tiết": "Có trong BOM nhưng không có trong XY", "Nguồn": "Tổng XY"})
        else:
            xy_row = match.iloc[0]
            cur_errs = []
            err_types = []
            
            # 1. Check Mô tả
            if super_clean(info['desc']) != super_clean(xy_row[c_xy_desc]):
                cur_errs.append(f"Mô tả lệch")
                err_types.append("Mô tả")
            
            # 2. Check P/N (So sánh PN của BOM với PN của XY)
            xy_pns = get_values(xy_row, ["Part Number", "P/N"])
            if info['pns'] and xy_pns and not (info['pns'] & xy_pns):
                cur_errs.append(f"P/N BOM {info['pns']} vs XY {xy_pns}")
                err_types.append("P/N")
                
            # 3. Check Hãng (Chỉ check nếu XY có cột Hãng thực sự)
            xy_mfrs = get_values(xy_row, ["Hãng", "Manufacturer"], exclude_keywords=["Part Number", "P/N", "PN"])
            if info['mfrs'] and xy_mfrs and not (info['mfrs'] & xy_mfrs):
                cur_errs.append(f"Hãng BOM {info['mfrs']} vs XY {xy_mfrs}")
                err_types.append("Hãng")

            if cur_errs:
                errors.append({
                    "Vị trí": pos,
                    "Loại lỗi": "Sai " + ", ".join(err_types),
                    "Chi tiết": " | ".join(cur_errs),
                    "Nguồn": xy_row.get("File Nguồn", "XY Data")
                })

    return pd.DataFrame(errors)

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="SMT Checker Fixed", layout="wide")
st.title("Đối soát BOM & XY Data (Fix lỗi so nhầm PN/Hãng)")

f_bom = st.file_uploader("1. Upload BOM", type=['xlsx'])
if f_bom:
    xls_bom = pd.ExcelFile(f_bom)
    sheet_bom = st.selectbox("Chọn Sheet BOM:", xls_bom.sheet_names)
    df_bom = pd.read_excel(f_bom, sheet_name=sheet_bom)

f_xys = st.file_uploader("2. Upload XY DATA", type=['xlsx'], accept_multiple_files=True)
if f_xys:
    list_xy = []
    for f in f_xys:
        t = pd.read_excel(f)
        t["File Nguồn"] = f.name
        list_xy.append(t)
    df_xy = pd.concat(list_xy, ignore_index=True)

if f_bom and f_xys:
    if st.button("🚀 Chạy đối soát"):
        res = full_cross_check(df_bom, df_xy)
        if isinstance(res, str): st.error(res)
        else:
            st.dataframe(res, use_container_width=True)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as wr: res.to_excel(wr, index=False)
            st.download_button("📥 Tải báo cáo", out.getvalue(), "Bao_cao_SMT_Fixed.xlsx")
