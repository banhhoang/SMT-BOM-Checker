import streamlit as st
import pandas as pd
import io

def clean_column_names(df):
    """Hàm tự động làm sạch tên cột: xóa khoảng trắng thừa, viết thường"""
    df.columns = [str(col).strip() for col in df.columns]
    return df

def full_cross_check(df_bom, df_xy):
    errors = []
    
    # Làm sạch tên cột ngay khi bắt đầu
    df_bom = clean_column_names(df_bom)
    df_xy = clean_column_names(df_xy)

    # Tìm tên cột chính xác (không sợ thừa thiếu khoảng trắng)
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    
    col_xy_desig = next((c for c in df_xy.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy.columns if "Description" in c), None)

    if not all([col_bom_desc, col_bom_pos, col_bom_qty, col_xy_desig, col_xy_desc]):
        return "Lỗi: Không tìm thấy các cột cần thiết trong file. Vui lòng kiểm tra lại tên cột BOM và XY Data."

    all_bom_positions = set()

    # CHIỀU 1: BOM -> XY DATA
    for _, row in df_bom.iterrows():
        if pd.isna(row[col_bom_pos]) or str(row[col_bom_pos]).strip() == "" or "Tích hợp" in str(row[col_bom_pos]):
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        bom_qty = row[col_bom_qty]
        pos_list = [p.strip() for p in str(row[col_bom_pos]).replace(';', ',').split(',') if p.strip()]
        all_bom_positions.update(pos_list)

        if len(pos_list) != bom_qty:
            errors.append({"Vị trí": row[col_bom_pos], "Lỗi": "Sai số lượng trong BOM", "Chi tiết": f"Ghi {bom_qty} nhưng đếm được {len(pos_list)}"})

        for pos in pos_list:
            match_xy = df_xy[df_xy[col_xy_desig] == pos]
            if match_xy.empty:
                errors.append({"Vị trí": pos, "Lỗi": "Thiếu trong XY Data", "Chi tiết": "Có trong BOM nhưng không có trong tọa độ SMT"})
            else:
                xy_desc = str(match_xy.iloc[0][col_xy_desc]).strip()
                if bom_desc.lower() != xy_desc.lower():
                    errors.append({"Vị trí": pos, "Lỗi": "Sai khác mô tả", "Chi tiết": f"BOM: {bom_desc} | XY: {xy_desc}"})

    # CHIỀU 2: XY DATA -> BOM
    for _, row in df_xy.iterrows():
        xy_pos = str(row[col_xy_desig]).strip()
        if xy_pos not in all_bom_positions:
            errors.append({"Vị trí": xy_pos, "Lỗi": "Thừa trong XY Data", "Chi tiết": "Vị trí này không có trong BOM sản xuất"})

    return pd.DataFrame(errors)

# Giao diện
st.set_page_config(page_title="SMT Checker", layout="wide")
st.title("Hệ thống đối soát BOM & XY DATA")

c1, c2 = st.columns(2)
with c1:
    file_bom = st.file_uploader("Upload BOM", type=['xlsx', 'csv'])
with c2:
    file_xy = st.file_uploader("Upload XY DATA", type=['xlsx', 'csv'])

if file_bom and file_xy:
    try:
        # Đọc file (dùng bản sao byte để tránh lỗi file đang mở)
        df_bom = pd.read_excel(file_bom) if file_bom.name.endswith('.xlsx') else pd.read_csv(file_bom)
        df_xy = pd.read_excel(file_xy) if file_xy.name.endswith('.xlsx') else pd.read_csv(file_xy)
        
        if st.button("Bắt đầu đối soát"):
            result = full_cross_check(df_bom, df_xy)
            if isinstance(result, str):
                st.error(result)
            elif result.empty:
                st.success("✅ Dữ liệu khớp 100%!")
            else:
                st.warning(f" tìm thấy {len(result)} lỗi")
                st.dataframe(result, use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result.to_excel(writer, index=False)
                st.download_button("Tải báo cáo lỗi", output.getvalue(), "Loi_SMT.xlsx")
    except Exception as e:
        st.error(f"Lỗi: {e}")
