import streamlit as st
import pandas as pd
import io
import re

# Từ khóa để nhận diện cột (Bạn có thể thêm từ khóa nếu file thay đổi)
KEYWORDS = {
    "bom_desc": ["Mô tả", "Description", "Yêu cầu kỹ thuật"],
    "bom_pos": ["Vị trí", "Designator", "VTLK"],
    "bom_qty": ["Số lượng", "Qty", "Quantity"],
    "pn": ["P/N", "Part Number", "MPN"],
    "mfr": ["Hãng", "Manufacturer", "Mfr"]
}

def super_clean(text):
    """Xóa tất cả ký tự đặc biệt để so sánh lõi dữ liệu"""
    if pd.isna(text): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

def find_column(df, keys):
    """Tự động tìm tên cột thực tế dựa trên danh sách từ khóa"""
    for col in df.columns:
        if any(k.lower() in str(col).lower() for k in keys):
            return col
    return None

def get_values(row, keys):
    """Lấy dữ liệu từ tất cả các cột liên quan đến PN hoặc Hãng"""
    vals = set()
    for col in row.index:
        if any(k.lower() in str(col).lower() for k in keys):
            v = str(row[col]).strip()
            if v and v.lower() not in ['nan', 'na', 'none', '0', '']:
                vals.add(v.upper())
    return vals

def full_cross_check(df_bom, df_xy):
    errors = []
    # 1. Làm sạch tên cột ngay lập tức
    df_bom.columns = [str(c).strip() for c in df_bom.columns]
    df_xy.columns = [str(c).strip() for c in df_xy.columns]

    # 2. Định vị các cột quan trọng
    c_bom_desc = find_column(df_bom, KEYWORDS["bom_desc"])
    c_bom_pos = find_column(df_bom, KEYWORDS["bom_pos"])
    c_bom_qty = find_column(df_bom, KEYWORDS["bom_qty"])
    
    c_xy_desig = find_column(df_xy, ["Designator", "Vị trí"])
    c_xy_desc = find_column(df_xy, ["Description", "Mô tả"])

    if not all([c_bom_desc, c_bom_pos, c_bom_qty, c_xy_desig, c_xy_desc]):
        missing = [k for k, v in {"Mô tả": c_bom_desc, "Vị trí": c_bom_pos, "Số lượng": c_bom_qty}.items() if v is None]
        return f"Lỗi: Không tìm thấy cột {missing} trong file của bạn."

    all_bom_pos = {}

    # --- DUYỆT BOM ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[c_bom_pos])
        if pd.isna(row[c_bom_pos]) or not pos_raw.strip() or "Tích hợp" in pos_raw:
            continue

        desc = str(row[c_bom_desc]).strip()
        try:
            qty = int(float(row[c_bom_qty]))
        except:
            qty = 0
            
        pns = get_values(row, KEYWORDS["pn"])
        mfrs = get_values(row, KEYWORDS["mfr"])
        
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        for p in pos_list:
            all_bom_pos[p] = {"desc": desc, "pns": pns, "mfrs": mfrs}

        if len(pos_list) != qty:
            errors.append({"Vị trí": pos_raw, "Loại lỗi": "Sai SL BOM", "Chi tiết": f"BOM ghi {qty} nhưng liệt kê {len(pos_list)}", "Nguồn": "BOM"})

    # --- SO KHỚP XY ---
    for pos, info in all_bom_pos.items():
        match = df_xy[df_xy[c_xy_desig] == pos]
        if match.empty:
            errors.append({"Vị trí": pos, "Loại lỗi": "Thiếu tọa độ", "Chi tiết": "Có trong BOM nhưng không có trong XY", "Nguồn": "Tổng hợp XY"})
        else:
            xy_row = match.iloc[0]
            cur_errs = []
            
            # Check Mô tả (Dùng super_clean để tránh lỗi dấu cách/phẩy)
            if super_clean(info['desc']) != super_clean(xy_row[c_xy_desc]):
                cur_errs.append(f"[Mô tả] BOM: '{info['desc']}' vs XY: '{xy_row[c_xy_desc]}'")
            
            # Check P/N và Hãng
            xy_pns = get_values(xy_row, KEYWORDS["pn"])
            if info['pns'] and xy_pns and not (info['pns'] & xy_pns):
                cur_errs.append(f"[P/N] BOM: {info['pns']} vs XY: {xy_pns}")
                
            xy_mfrs = get_values(xy_row, KEYWORDS["mfr"])
            if info['mfrs'] and xy_mfrs and not (info['mfrs'] & xy_mfrs):
                cur_errs.append(f"[Hãng] BOM: {info['mfrs']} vs XY: {xy_mfrs}")

            if cur_errs:
                errors.append({"Vị trí": pos, "Loại lỗi": "Sai thông tin", "Chi tiết": " | ".join(cur_errs), "Nguồn": xy_row.get("File Nguồn", "XY Data")})

    # --- CHECK THỪA XY ---
    for _, row in df_xy.iterrows():
        p = str(row[c_xy_desig]).strip()
        if p not in all_bom_pos:
            errors.append({"Vị trí": p, "Loại lỗi": "Thừa trong XY", "Chi tiết": "Có tọa độ nhưng không có trong BOM", "Nguồn": row.get("File Nguồn", "XY Data")})

    return pd.DataFrame(errors)

# --- UI ---
st.set_page_config(page_title="SMT Checker Ultimate", layout="wide")
st.title("Đối soát BOM & XY Data (Bản ổn định)")

f_bom = st.file_uploader("1. Tải lên BOM", type=['xlsx', 'csv'])
f_xys = st.file_uploader("2. Tải lên (các) file XY DATA", type=['xlsx', 'csv'], accept_multiple_files=True)

if f_bom and f_xys:
    try:
        df_bom = pd.read_excel(f_bom) if f_bom.name.endswith('.xlsx') else pd.read_csv(f_bom)
        list_xy = []
        for f in f_xys:
            t = pd.read_excel(f) if f.name.endswith('.xlsx') else pd.read_csv(f)
            t["File Nguồn"] = f.name
            list_xy.append(t)
        df_xy = pd.concat(list_xy, ignore_index=True)
        
        if st.button("🚀 Bắt đầu kiểm tra"):
            res = full_cross_check(df_bom, df_xy)
            if isinstance(res, str): st.error(res)
            elif res.empty: st.success("✅ Tuyệt vời! Dữ liệu khớp 100%.")
            else:
                st.warning(f"Tìm thấy {len(res)} lỗi.")
                st.dataframe(res, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr: res.to_excel(wr, index=False)
                st.download_button("📥 Tải báo cáo lỗi", out.getvalue(), "Bao_cao_SMT.xlsx")
    except Exception as e:
        st.error(f"Lỗi: {e}")
