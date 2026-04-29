import streamlit as st
import pandas as pd
import io
import re

# 1. Hàm làm sạch chuỗi cực mạnh (Xóa dấu cách, ký tự đặc biệt, đưa về chữ thường)
def super_clean(text):
    if pd.isna(text): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

def find_column(df, keywords):
    """Tự động tìm tên cột thực tế dựa trên từ khóa gợi nhớ"""
    for col in df.columns:
        col_clean = super_clean(col)
        for k in keywords:
            if super_clean(k) in col_clean:
                return col
    return None

def get_values_from_row(row, keywords):
    """Lấy dữ liệu từ các cột liên quan đến P/N hoặc Hãng"""
    vals = set()
    for col in row.index:
        if any(k.lower() in str(col).lower() for k in keywords):
            v = str(row[col]).strip()
            if v and v.lower() not in ['nan', 'na', 'none', '0', '']:
                vals.add(v.upper())
    return vals

def full_cross_check(df_bom, df_xy):
    errors = []
    
    # 2. Định vị các cột bằng từ khóa (Không sợ thừa dấu cách)
    c_bom_desc = find_column(df_bom, ["Mô tả", "Description", "Yêu cầu kỹ thuật"])
    c_bom_pos = find_column(df_bom, ["Vị trí", "Designator", "VTLK"])
    c_bom_qty = find_column(df_bom, ["Số lượng", "Qty", "Quantity"])
    
    c_xy_desig = find_column(df_xy, ["Designator", "Vị trí"])
    c_xy_desc = find_column(df_xy, ["Description", "Mô tả"])

    if not all([c_bom_desc, c_bom_pos, c_bom_qty, c_xy_desig, c_xy_desc]):
        return "Lỗi: App không tìm thấy cột 'Mô tả' hoặc 'Vị trí' trong file. Hãy kiểm tra lại tiêu đề Excel."

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
            
        pns = get_values_from_row(row, ["P/N", "Part Number"])
        mfrs = get_values_from_row(row, ["Hãng", "Manufacturer"])
        
        # Tách danh sách vị trí: C1, C2 -> [C1, C2]
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        for p in pos_list:
            all_bom_pos[p] = {"desc": desc, "pns": pns, "mfrs": mfrs}

        if len(pos_list) != qty:
            errors.append({"Vị trí": pos_raw, "Loại lỗi": "Sai SL BOM", "Chi tiết": f"Ghi {qty} nhưng đếm {len(pos_list)}", "Nguồn": "BOM"})

    # --- SO KHỚP VỚI XY DATA ---
    for pos, info in all_bom_pos.items():
        match = df_xy[df_xy[c_xy_desig] == pos]
        if match.empty:
            errors.append({"Vị trí": pos, "Loại lỗi": "Thiếu tọa độ", "Chi tiết": "Có trong BOM nhưng không có trong XY", "Nguồn": "Tổng hợp XY"})
        else:
            xy_row = match.iloc[0]
            cur_errs = []
            
            # So sánh Mô tả (Dùng super_clean để bỏ qua dấu cách/phẩy thừa)
            if super_clean(info['desc']) != super_clean(xy_row[c_xy_desc]):
                cur_errs.append(f"[Mô tả] BOM: '{info['desc']}' vs XY: '{xy_row[c_xy_desc]}'")
            
            # So sánh P/N và Hãng
            xy_pns = get_values_from_row(xy_row, ["P/N", "Part Number"])
            if info['pns'] and xy_pns and not (info['pns'] & xy_pns):
                cur_errs.append(f"[P/N] BOM: {info['pns']} vs XY: {xy_pns}")
                
            xy_mfrs = get_values_from_row(xy_row, ["Hãng", "Manufacturer"])
            if info['mfrs'] and xy_mfrs and not (info['mfrs'] & xy_mfrs):
                cur_errs.append(f"[Hãng] BOM: {info['mfrs']} vs XY: {xy_mfrs}")

            if cur_errs:
                errors.append({"Vị trí": pos, "Loại lỗi": "Sai thông tin", "Chi tiết": " | ".join(cur_errs), "Nguồn": xy_row.get("File Nguồn", "XY Data")})

    # --- CHECK LINH KIỆN THỪA TRÊN XY ---
    for _, row in df_xy.iterrows():
        p = str(row[c_xy_desig]).strip()
        if p not in all_bom_pos:
            errors.append({"Vị trí": p, "Loại lỗi": "Thừa trong XY", "Chi tiết": "Có tọa độ nhưng không có trong BOM", "Nguồn": row.get("File Nguồn", "XY Data")})

    return pd.DataFrame(errors)

# --- GIAO DIỆN ---
st.set_page_config(page_title="SMT Checker Fixed", layout="wide")
st.title("Đối soát BOM & XY Data (Bản chống lỗi dấu cách)")

f_bom = st.file_uploader("1. Upload BOM", type=['xlsx', 'csv'])
f_xys = st.file_uploader("2. Upload XY DATA", type=['xlsx', 'csv'], accept_multiple_files=True)

if f_bom and f_xys:
    try:
        # Đọc dữ liệu
        df_bom = pd.read_excel(f_bom) if f_bom.name.endswith('.xlsx') else pd.read_csv(f_bom)
        
        list_xy = []
        for f in f_xys:
            t = pd.read_excel(f) if f.name.endswith('.xlsx') else pd.read_csv(f)
            t["File Nguồn"] = f.name
            list_xy.append(t)
        df_xy = pd.concat(list_xy, ignore_index=True)
        
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
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr: res.to_excel(wr, index=False)
                st.download_button("📥 Tải báo cáo lỗi", out.getvalue(), "Bao_cao_SMT.xlsx")
    except Exception as e:
        st.error(f"Lỗi đọc file: {e}")
