import streamlit as st
import pandas as pd
import io
import re

# 1. Các hàm xử lý dữ liệu lõi
def super_clean(text):
    """Xóa tất cả ký tự đặc biệt, dấu cách để so sánh lõi"""
    if pd.isna(text): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

def find_column(df, keywords):
    """Tìm tên cột thực tế dựa trên từ khóa gợi nhớ"""
    for col in df.columns:
        col_clean = super_clean(col)
        for k in keywords:
            if super_clean(k) in col_clean:
                return col
    return None

def get_values(row, keywords, exclude_keywords=None):
    """Lấy dữ liệu từ tất cả các cột liên quan đến PN hoặc Hãng, có bộ lọc loại trừ"""
    vals = set()
    for col in row.index:
        col_name = str(col).lower()
        if any(k.lower() in col_name for k in keywords):
            if exclude_keywords and any(ex.lower() in col_name for ex in exclude_keywords):
                continue
            v = str(row[col]).strip()
            if v and v.lower() not in ['nan', 'na', 'none', '0', '']:
                vals.add(v.upper())
    return vals

def get_correct_df(file, sheet_name=None):
    """Tự động tìm dòng chứa tiêu đề (Row 0, 1 hoặc 2...)"""
    df_preview = pd.read_excel(file, sheet_name=sheet_name, header=None, nrows=10)
    header_row = 0
    for i, row in df_preview.iterrows():
        row_str = " ".join([str(x) for x in row.values])
        # Tìm dòng có chứa các từ khóa tiêu chuẩn
        if any(k in row_str for k in ["Mô tả", "Vị trí", "Designator", "Description"]):
            header_row = i
            break
    return pd.read_excel(file, sheet_name=sheet_name, header=header_row)

def full_cross_check(df_bom, df_xy):
    errors = []
    # Định vị các cột quan trọng
    c_bom_desc = find_column(df_bom, ["Mô tả", "Description", "Yêu cầu kỹ thuật"])
    c_bom_pos = find_column(df_bom, ["Vị trí", "Designator", "VTLK"])
    c_bom_qty = find_column(df_bom, ["Số lượng", "Qty"])
    
    c_xy_desig = find_column(df_xy, ["Designator", "Vị trí"])
    c_xy_desc = find_column(df_xy, ["Description", "Mô tả"])

    # Kiểm tra cột thiếu (Sửa lỗi hiển thị [] trống)
    missing = []
    if not c_bom_desc: missing.append("Mô tả (BOM)")
    if not c_bom_pos: missing.append("Vị trí (BOM)")
    if not c_bom_qty: missing.append("Số lượng (BOM)")
    if not c_xy_desig: missing.append("Designator (XY)")
    
    if missing:
        return f"Lỗi: Không tìm thấy các cột {missing} trong file đã chọn. Hãy kiểm tra lại dòng tiêu đề."

    all_bom_pos = {}

    # --- DUYỆT FILE BOM ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[c_bom_pos])
        if pd.isna(row[c_bom_pos]) or not pos_raw.strip() or "Tích hợp" in pos_raw:
            continue

        desc = str(row[c_bom_desc]).strip()
        try:
            qty = int(float(row[c_bom_qty]))
        except:
            qty = 0
            
        pns = get_values(row, ["P/N", "Part Number"])
        mfrs = get_values(row, ["Hãng", "Manufacturer"], exclude_keywords=["Part Number", "P/N", "PN"])
        
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        for p in pos_list:
            all_bom_pos[p] = {"desc": desc, "pns": pns, "mfrs": mfrs, "pos_raw": pos_raw, "qty": qty, "actual_count": len(pos_list)}

        if len(pos_list) != qty:
            errors.append({
                "Vị trí": pos_raw,
                "Loại lỗi": "Sai SL BOM",
                "Chi tiết": f"BOM ghi {qty} nhưng liệt kê {len(pos_list)} vị trí",
                "Nguồn": "File BOM"
            })

    # --- SO KHỚP VỚI XY DATA ---
    for pos, info in all_bom_pos.items():
        match = df_xy[df_xy[c_xy_desig] == pos]
        if match.empty:
            errors.append({
                "Vị trí": pos,
                "Loại lỗi": "Thiếu tọa độ",
                "Chi tiết": "Có trong BOM nhưng không có trong file XY",
                "Nguồn": "Tổng hợp XY"
            })
        else:
            xy_row = match.iloc[0]
            cur_errs = []
            err_types = []
            
            # 1. Check Mô tả (Chỉ check nếu file XY có cột Mô tả)
            if c_xy_desc and super_clean(info['desc']) != super_clean(xy_row[c_xy_desc]):
                cur_errs.append(f"Mô tả lệch")
                err_types.append("Mô tả")
            
            # 2. Check P/N
            xy_pns = get_values(xy_row, ["P/N", "Part Number"])
            if info['pns'] and xy_pns and not (info['pns'] & xy_pns):
                cur_errs.append(f"P/N BOM {info['pns']} vs XY {xy_pns}")
                err_types.append("P/N")
                
            # 3. Check Hãng
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

    # --- CHECK LINH KIỆN THỪA ---
    for _, row in df_xy.iterrows():
        p = str(row[c_xy_desig]).strip()
        if p not in all_bom_pos and p.lower() not in ['nan', 'na', '']:
            errors.append({
                "Vị trí": p,
                "Loại lỗi": "Thừa trong XY",
                "Chi tiết": "Vị trí có tọa độ nhưng không nằm trong BOM",
                "Nguồn": row.get("File Nguồn", "XY Data")
            })

    return pd.DataFrame(errors)

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="SMT Checker Pro", layout="wide")
st.title("Hệ thống Đối soát BOM & XY Data")

f_bom = st.file_uploader("1. Tải lên file BOM", type=['xlsx'])
df_bom = None
if f_bom:
    xls_bom = pd.ExcelFile(f_bom)
    sheet_bom = st.selectbox("Chọn Sheet chứa dữ liệu BOM:", xls_bom.sheet_names, index=0)
    # Sửa: Sử dụng get_correct_df để tự tìm dòng tiêu đề
    df_bom = get_correct_df(f_bom, sheet_name=sheet_bom)

f_xys = st.file_uploader("2. Tải lên (các) file XY DATA", type=['xlsx'], accept_multiple_files=True)
df_xy = None
if f_xys:
    list_xy = []
    for f in f_xys:
        # Sửa: Sử dụng get_correct_df để đảm bảo tìm đúng tiêu đề trong file XY
        t = get_correct_df(f)
        t["File Nguồn"] = f.name
        list_xy.append(t)
    df_xy = pd.concat(list_xy, ignore_index=True)

if df_bom is not None and df_xy is not None:
    if st.button("🚀 Bắt đầu đối soát"):
        res = full_cross_check(df_bom, df_xy)
        if isinstance(res, str):
            st.error(res)
        elif res.empty:
            st.success("✅ Tuyệt vời! Dữ liệu khớp 100%.")
        else:
            st.warning(f"Tìm thấy {len(res)} lỗi.")
            st.dataframe(res, use_container_width=True)
            
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
                res.to_excel(wr, index=False)
            st.download_button("📥 Tải báo cáo lỗi (.xlsx)", out.getvalue(), "Bao_cao_loi_SMT.xlsx")
