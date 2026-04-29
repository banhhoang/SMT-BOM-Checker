import streamlit as st
import pandas as pd
import io

def clean_column_names(df):
    df.columns = [str(col).strip() for col in df.columns]
    return df

def get_all_values_from_row(row, keywords):
    """Lấy tập hợp các giá trị từ các cột có tên chứa từ khóa"""
    values = set()
    for col in row.index:
        if any(key.lower() in str(col).lower() for key in keywords):
            val = str(row[col]).strip()
            if val and val.lower() not in ['na', 'nan', 'none', '', '0']:
                values.add(val.upper()) # Chuyển về chữ hoa để dễ so sánh
    return values

def full_cross_check(df_bom, df_xy_combined):
    errors = []
    df_bom = clean_column_names(df_bom)
    df_xy_combined = clean_column_names(df_xy_combined)

    # Tìm cột chính
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    col_xy_desig = next((c for c in df_xy_combined.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy_combined.columns if "Description" in c), None)
    col_source = "File Nguồn" 

    PN_KEYWORDS = ["P/N", "Part Number"]
    MFR_KEYWORDS = ["Hãng sản xuất", "Manufacturer", "Mfr"]

    all_bom_positions = {}

    # --- CHIỀU 1: TỪ BOM SANG XY DATA ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[col_bom_pos])
        if pd.isna(row[col_bom_pos]) or pos_raw.strip() == "" or "Tích hợp" in pos_raw:
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        bom_qty = int(row[col_bom_qty]) if pd.notna(row[col_bom_qty]) else 0
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        bom_pns = get_all_values_from_row(row, PN_KEYWORDS)
        bom_mfrs = get_all_values_from_row(row, MFR_KEYWORDS)
        
        for p in pos_list:
            all_bom_positions[p] = {"desc": bom_desc, "pns": bom_pns, "mfrs": bom_mfrs}

        if len(pos_list) != bom_qty:
            errors.append({
                "Vị trí": pos_raw,
                "Loại lỗi": "Sai số lượng BOM",
                "Chi tiết": f"BOM ghi {bom_qty} nhưng đếm thực tế {len(pos_list)} vị trí",
                "Nguồn lỗi": "File BOM"
            })

        for pos in pos_list:
            match_xy = df_xy_combined[df_xy_combined[col_xy_desig] == pos]
            if match_xy.empty:
                errors.append({
                    "Vị trí": pos,
                    "Loại lỗi": "Thiếu trong XY Data",
                    "Chi tiết": "Linh kiện có trong BOM nhưng không tìm thấy tọa độ",
                    "Nguồn lỗi": "Tổng hợp XY"
                })
            else:
                xy_row = match_xy.iloc[0]
                file_name = xy_row[col_source]
                
                # Danh sách chứa các lỗi phát hiện được tại vị trí này
                current_errors = []
                
                # 1. Check Mô tả
                xy_desc = str(xy_row[col_xy_desc]).strip()
                if bom_desc.lower() != xy_desc.lower():
                    current_errors.append(f"[Sai Mô tả] BOM: '{bom_desc}' vs XY: '{xy_desc}'")
                
                # 2. Check P/N
                xy_pns = get_all_values_from_row(xy_row, PN_KEYWORDS)
                if bom_pns and xy_pns and not (bom_pns & xy_pns):
                    current_errors.append(f"[Sai P/N] BOM: {bom_pns} vs XY: {xy_pns}")
                
                # 3. Check Hãng
                xy_mfrs = get_all_values_from_row(xy_row, MFR_KEYWORDS)
                if bom_mfrs and xy_mfrs and not (bom_mfrs & xy_mfrs):
                    current_errors.append(f"[Sai Hãng] BOM: {bom_mfrs} vs XY: {xy_mfrs}")

                # Nếu có bất kỳ lỗi nào, gộp lại thành 1 dòng duy nhất
                if current_errors:
                    errors.append({
                        "Vị trí": pos,
                        "Loại lỗi": "Sai khác thông tin linh kiện",
                        "Chi tiết": " | ".join(current_errors),
                        "Nguồn lỗi": f"File: {file_name}"
                    })

    # --- CHIỀU 2: TỪ XY DATA SANG BOM ---
    for _, row in df_xy_combined.iterrows():
        xy_pos = str(row[col_xy_desig]).strip()
        if xy_pos not in all_bom_positions:
            errors.append({
                "Vị trí": xy_pos,
                "Loại lỗi": "Thừa trong XY Data",
                "Chi tiết": "Vị trí có tọa độ nhưng không nằm trong danh mục BOM",
                "Nguồn lỗi": f"File: {row[col_source]}"
            })

    return pd.DataFrame(errors)

# --- GIAO DIỆN ---
st.set_page_config(page_title="SMT Checker Pro", layout="wide")
st.title("Đối soát BOM & XY Data - Tổng hợp lỗi")

f_bom = st.file_uploader("1. Upload file BOM Tổng", type=['xlsx', 'csv'])
f_xys = st.file_uploader("2. Upload các file XY DATA", type=['xlsx', 'csv'], accept_multiple_files=True)

if f_bom and f_xys:
    try:
        df_bom = pd.read_excel(f_bom) if f_bom.name.endswith('.xlsx') else pd.read_csv(f_bom)
        list_xy = []
        for f in f_xys:
            t = pd.read_excel(f) if f.name.endswith('.xlsx') else pd.read_csv(f)
            t = clean_column_names(t)
            t["File Nguồn"] = f.name
            list_xy.append(t)
        df_combined = pd.concat(list_xy, ignore_index=True)

        if st.button("🚀 Kiểm tra toàn bộ"):
            res = full_cross_check(df_bom, df_combined)
            if isinstance(res, str):
                st.error(res)
            elif res.empty:
                st.success("✅ Dữ liệu khớp 100%!")
            else:
                st.warning(f"Tìm thấy {len(res)} vị trí có lỗi.")
                st.dataframe(res, use_container_width=True)
                
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
                    res.to_excel(wr, index=False)
                st.download_button("Tải báo cáo lỗi", out.getvalue(), "Bao_cao_tong_hop_loi.xlsx")
    except Exception as e:
        st.error(f"Lỗi: {e}")
