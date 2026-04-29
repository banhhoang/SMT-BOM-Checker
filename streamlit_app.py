import streamlit as st
import pandas as pd
import io

def clean_column_names(df):
    """Làm sạch tên cột: xóa khoảng trắng và chuẩn hóa"""
    df.columns = [str(col).strip() for col in df.columns]
    return df

def get_all_values_from_row(row, keywords):
    """Hàm lấy tất cả giá trị từ các cột có chứa từ khóa (PN, Hãng...) và trả về một tập hợp (set)"""
    values = set()
    for col in row.index:
        # Kiểm tra nếu tên cột chứa bất kỳ từ khóa nào (không phân biệt hoa thường)
        if any(key.lower() in str(col).lower() for key in keywords):
            val = str(row[col]).strip()
            # Loại bỏ các giá trị rỗng hoặc không có dữ liệu (NA, nan)
            if val and val.lower() not in ['na', 'nan', 'none', '']:
                values.add(val.lower())
    return values

def full_cross_check(df_bom, df_xy_combined):
    errors = []
    df_bom = clean_column_names(df_bom)
    df_xy_combined = clean_column_names(df_xy_combined)

    # Xác định các cột cơ bản
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    
    col_xy_desig = next((c for c in df_xy_combined.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy_combined.columns if "Description" in c), None)
    col_source = "File Nguồn" 

    # Từ khóa để tìm cột P/N và Hãng sản xuất
    PN_KEYWORDS = ["P/N", "Part Number"]
    MFR_KEYWORDS = ["Hãng sản xuất", "Manufacturer", "Mfr"]

    if not all([col_bom_desc, col_bom_pos, col_bom_qty, col_xy_desig, col_xy_desc]):
        return "Lỗi: File thiếu cột cần thiết (Mô tả, Vị trí, Số lượng hoặc Designator/Description)."

    all_bom_positions = {}

    # --- CHIỀU 1: TỪ BOM SANG XY DATA ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[col_bom_pos])
        if pd.isna(row[col_bom_pos]) or pos_raw.strip() == "" or "Tích hợp" in pos_raw:
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        bom_qty = int(row[col_bom_qty]) if pd.notna(row[col_bom_qty]) else 0
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        # Lấy tập hợp P/N và Hãng từ BOM cho dòng này
        bom_pns = get_all_values_from_row(row, PN_KEYWORDS)
        bom_mfrs = get_all_values_from_row(row, MFR_KEYWORDS)
        
        for p in pos_list:
            all_bom_positions[p] = {"desc": bom_desc, "pns": bom_pns, "mfrs": bom_mfrs}

        # 1. Kiểm tra số lượng
        if len(pos_list) != bom_qty:
            errors.append({"Vị trí": pos_raw, "Loại lỗi": "Sai số lượng BOM", "Chi tiết": f"Ghi {bom_qty} nhưng đếm {len(pos_list)}", "Nguồn": "BOM"})

        # 2. Kiểm tra từng vị trí so với XY
        for pos in pos_list:
            match_xy = df_xy_combined[df_xy_combined[col_xy_desig] == pos]
            if match_xy.empty:
                errors.append({"Vị trí": pos, "Loại lỗi": "Thiếu trong XY Data", "Chi tiết": "Không thấy tọa độ", "Nguồn": "Tổng hợp XY"})
            else:
                xy_row = match_xy.iloc[0]
                file_name = xy_row[col_source]
                
                # Check Mô tả
                xy_desc = str(xy_row[col_xy_desc]).strip()
                if bom_desc.lower() != xy_desc.lower():
                    errors.append({"Vị trí": pos, "Loại lỗi": "Sai Mô tả", "Chi tiết": f"BOM: {bom_desc} | XY: {xy_desc}", "Nguồn": file_name})
                
                # Check P/N (Phải có ít nhất 1 P/N trùng nhau)
                xy_pns = get_all_values_from_row(xy_row, PN_KEYWORDS)
                if bom_pns and xy_pns and not (bom_pns & xy_pns):
                    errors.append({
                        "Vị trí": pos, "Loại lỗi": "Sai Part Number (P/N)", 
                        "Chi tiết": f"BOM: {bom_pns} | XY: {xy_pns}", "Nguồn": file_name
                    })
                
                # Check Hãng (Phải có ít nhất 1 Hãng trùng nhau)
                xy_mfrs = get_all_values_from_row(xy_row, MFR_KEYWORDS)
                if bom_mfrs and xy_mfrs and not (bom_mfrs & xy_mfrs):
                    errors.append({
                        "Vị trí": pos, "Loại lỗi": "Sai Nhà sản xuất", 
                        "Chi tiết": f"BOM: {bom_mfrs} | XY: {xy_mfrs}", "Nguồn": file_name
                    })

    # --- CHIỀU 2: TỪ XY DATA SANG BOM (Linh kiện thừa) ---
    for _, row in df_xy_combined.iterrows():
        xy_pos = str(row[col_xy_desig]).strip()
        if xy_pos not in all_bom_positions:
            errors.append({"Vị trí": xy_pos, "Loại lỗi": "Thừa trong XY Data", "Chi tiết": "Có tọa độ nhưng không có trong BOM", "Nguồn": row[col_source]})

    return pd.DataFrame(errors)

# --- GIAO DIỆN ---
st.set_page_config(page_title="SMT Pro Checker v2", layout="wide")
st.title("Đối soát BOM & XY Data (Check P/N & Hãng)")

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

        if st.button("🚀 Bắt đầu đối soát"):
            res = full_cross_check(df_bom, df_combined)
            if isinstance(res, str):
                st.error(res)
            elif res.empty:
                st.success("✅ Dữ liệu khớp 100%!")
            else:
                st.warning(f"Tìm thấy {len(res)} lỗi.")
                st.dataframe(res, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
                    res.to_excel(wr, index=False)
                st.download_button("Tải báo cáo lỗi", out.getvalue(), "Bao_cao_SMT_Chi_tiet.xlsx")
    except Exception as e:
        st.error(f"Lỗi: {e}")
