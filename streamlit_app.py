import streamlit as st
import pandas as pd
import io

def clean_column_names(df):
    """Xóa khoảng trắng thừa ở tên cột để tránh lỗi KeyError"""
    df.columns = [str(col).strip() for col in df.columns]
    return df

def full_cross_check(df_bom, df_xy_combined):
    errors = []
    df_bom = clean_column_names(df_bom)
    df_xy_combined = clean_column_names(df_xy_combined)

    # Tự động tìm tên cột (không phân biệt hoa thường/khoảng trắng)
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    
    col_xy_desig = next((c for c in df_xy_combined.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy_combined.columns if "Description" in c), None)
    col_source = "File Nguồn" 

    if not all([col_bom_desc, col_bom_pos, col_bom_qty, col_xy_desig, col_xy_desc]):
        return "Lỗi: File của bạn thiếu cột cần thiết (Mô tả, Vị trí VTLK, Số lượng hoặc Designator/Description)."

    all_bom_positions = {}

    # --- CHIỀU 1: TỪ BOM SANG XY DATA ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[col_bom_pos])
        # pd.isna đã được định nghĩa nhờ 'import pandas as pd' ở trên
        if pd.isna(row[col_bom_pos]) or pos_raw.strip() == "" or "Tích hợp" in pos_raw:
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        bom_qty = int(row[col_bom_qty]) if pd.notna(row[col_bom_qty]) else 0
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        for p in pos_list:
            all_bom_positions[p] = bom_desc

        if len(pos_list) != bom_qty:
            errors.append({
                "Vị trí": pos_raw,
                "Loại lỗi": "Sai số lượng BOM",
                "Chi tiết": f"BOM ghi {bom_qty} nhưng đếm được {len(pos_list)}",
                "Nguồn lỗi": "File BOM"
            })

        for pos in pos_list:
            match_xy = df_xy_combined[df_xy_combined[col_xy_desig] == pos]
            if match_xy.empty:
                errors.append({
                    "Vị trí": pos,
                    "Loại lỗi": "Thiếu trong XY Data",
                    "Chi tiết": "Linh kiện có trong BOM nhưng không thấy ở file tọa độ nào.",
                    "Nguồn lỗi": "Tổng hợp XY"
                })
            else:
                xy_desc = str(match_xy.iloc[0][col_xy_desc]).strip()
                file_name = match_xy.iloc[0][col_source]
                if bom_desc.lower() != xy_desc.lower():
                    errors.append({
                        "Vị trí": pos,
                        "Loại lỗi": "Sai mô tả",
                        "Chi tiết": f"BOM: {bom_desc} | XY: {xy_desc}",
                        "Nguồn lỗi": f"File: {file_name}"
                    })

    # --- CHIỀU 2: TỪ XY DATA SANG BOM ---
    for _, row in df_xy_combined.iterrows():
        xy_pos = str(row[col_xy_desig]).strip()
        file_name = row[col_source]
        if xy_pos not in all_bom_positions:
            errors.append({
                "Vị trí": xy_pos,
                "Loại lỗi": "Thừa trong XY Data",
                "Chi tiết": "Vị trí này có tọa độ nhưng không có trong BOM tổng.",
                "Nguồn lỗi": f"File: {file_name}"
            })

    return pd.DataFrame(errors)

# --- GIAO DIỆN ---
st.set_page_config(page_title="SMT Pro Checker", layout="wide")
st.title("Đối soát BOM Tổng & XY Data Đa Mạch")

f_bom = st.file_uploader("1. Upload file BOM Tổng", type=['xlsx', 'csv'])
f_xys = st.file_uploader("2. Upload các file XY DATA", type=['xlsx', 'csv'], accept_multiple_files=True)

if f_bom and f_xys:
    try:
        # Đọc BOM
        df_bom = pd.read_excel(f_bom) if f_bom.name.endswith('.xlsx') else pd.read_csv(f_bom)
        
        # Đọc nhiều file XY
        list_xy = []
        for f in f_xys:
            t = pd.read_excel(f) if f.name.endswith('.xlsx') else pd.read_csv(f)
            t = clean_column_names(t)
            t["File Nguồn"] = f.name
            list_xy.append(t)
        
        df_combined = pd.concat(list_xy, ignore_index=True)

        if st.button("Bắt đầu đối soát"):
            res = full_cross_check(df_bom, df_combined)
            if isinstance(res, str):
                st.error(res)
            elif res.empty:
                st.success("✅ Tuyệt vời! Dữ liệu khớp hoàn toàn.")
            else:
                st.warning(f"Tìm thấy {len(res)} lỗi.")
                st.dataframe(res, use_container_width=True)
                
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
                    res.to_excel(wr, index=False)
                st.download_button("Tải báo cáo lỗi", out.getvalue(), "Bao_cao_SMT.xlsx")
    except Exception as e:
        st.error(f"Lỗi hệ thống: {e}")
