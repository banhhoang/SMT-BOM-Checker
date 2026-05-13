import streamlit as st
import pandas as pd
import io
import re

# 1. Hàm làm sạch chuỗi cực mạnh
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
            # Lọc giá trị rỗng hoặc mặc định
            if not v or v.lower() in ['nan', 'na', 'none', '0', '']:
                continue
            
            # --- PHẦN SỬA ĐỔI: Loại bỏ các chuỗi mẫu không phải P/N thật ---
            # Nếu chuỗi nằm trong ngoặc < > và có chứa chữ "part number" thì bỏ qua
            if v.startswith('<') and v.endswith('>') and "part number" in v.lower():
                continue
            
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
        missing = []
        if not c_bom_desc: missing.append("Mô tả (BOM)")
        if not c_bom_pos: missing.append("Vị trí (BOM)")
        if not c_bom_qty: missing.append("Số lượng (BOM)")
        return f"Lỗi: Không tìm thấy các cột {missing} trong Sheet đã chọn."

    all_bom_pos = {}
    
    # --- PHẦN THÊM MỚI: THEO DÕI TRÙNG P/N TRONG BOM ---
    pn_tracker = {} # Lưu {Mã_PN: [Danh sách các dòng/vị trí chứa mã đó]}

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
            
        # P/N của BOM: Lấy các cột P/N, Part Number
        pns = get_values(row, ["P/N", "Part Number"])
        
        # --- LOGIC KIỂM TRA TRÙNG P/N ---
        for pn in pns:
            if pn not in pn_tracker:
                pn_tracker[pn] = []
            pn_tracker[pn].append(pos_raw)
        
        # Hãng của BOM
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

    # --- KIỂM TRA P/N TRÙNG SAU KHI QUÉT XONG ---
    for pn, occurrences in pn_tracker.items():
        if len(occurrences) > 1:
            errors.append({
                "Vị trí": "Nhiều dòng",
                "Loại lỗi": "Trùng P/N trong BOM",
                "Chi tiết": f"Mã P/N '{pn}' bị khai báo tách rời ở các cụm vị trí: {'; '.join(occurrences)}",
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
            
            if super_clean(info['desc']) != super_clean(xy_row[c_xy_desc]):
                cur_errs.append(f"Mô tả: BOM '{info['desc']}' vs XY '{xy_row[c_xy_desc]}'")
                err_types.append("Mô tả")
            
            xy_pns = get_values(xy_row, ["P/N", "Part Number"])
            if info['pns'] and xy_pns and not (info['pns'] & xy_pns):
                cur_errs.append(f"P/N: BOM {info['pns']} vs XY {xy_pns}")
                err_types.append("P/N")
                
            xy_mfrs = get_values(xy_row, ["Hãng", "Manufacturer"], exclude_keywords=["Part Number", "P/N", "PN"])
            if info['mfrs'] and xy_mfrs and not (info['mfrs'] & xy_mfrs):
                cur_errs.append(f"Hãng: BOM {info['mfrs']} vs XY {xy_mfrs}")
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
    df_bom = pd.read_excel(f_bom, sheet_name=sheet_bom)

f_xys = st.file_uploader("2. Tải lên (các) file XY DATA", type=['xlsx'], accept_multiple_files=True)
df_xy = None
if f_xys:
    list_xy = []
    for f in f_xys:
        t = pd.read_excel(f)
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
