import streamlit as st
import pandas as pd
import io

def clean_column_names(df):
    """Xóa khoảng trắng thừa ở đầu/cuối tên cột"""
    df.columns = [str(col).strip() for col in df.columns]
    return df

def full_cross_check(df_bom, df_xy_combined):
    errors = []
    df_bom = clean_column_names(df_bom)
    df_xy_combined = clean_column_names(df_xy_combined)

    # Tự động tìm tên cột phù hợp
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    
    col_xy_desig = next((c for c in df_xy_combined.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy_combined.columns if "Description" in c), None)
    col_source = "File Nguồn" # Cột do mình tự tạo ra lúc đọc file

    if not all([col_bom_desc, col_bom_pos, col_bom_qty, col_xy_desig, col_xy_desc]):
        return "Lỗi: Không tìm thấy các cột cần thiết. Hãy kiểm tra lại tiêu đề file BOM hoặc XY."

    all_bom_positions = {} # Dùng dict để lưu {vị trí: mô tả}

    # --- CHIỀU 1: KIỂM TRA TỪ BOM SANG CÁC FILE XY ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[col_bom_pos])
        if pd.isna(pos_raw) or pos_raw.strip() == "" or "Tích hợp" in pos_raw:
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        bom_qty = row[col_bom_qty]
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        
        # Lưu vào danh sách tổng để đối chiếu chiều ngược lại
        for p in pos_list:
            all_bom_positions[p] = bom_desc

        # Kiểm tra số lượng nội bộ BOM
        if len(pos_list) != bom_qty:
            errors.append({
                "Vị trí": pos_raw,
                "Loại lỗi": "Sai số lượng BOM",
                "Chi tiết": f"BOM ghi {bom_qty} nhưng liệt kê {len(pos_list)} vị trí.",
                "Nguồn lỗi": "File BOM"
            })

        # Kiểm tra từng vị trí xem có trong bất kỳ file XY nào không
        for pos in pos_list:
            match_xy = df_xy_combined[df_xy_combined[col_xy_desig] == pos]
            
            if match_xy.empty:
                errors.append({
                    "Vị trí": pos,
                    "Loại lỗi": "Thiếu trong XY Data",
                    "Chi tiết": "Linh kiện có trong BOM nhưng không tìm thấy ở bất kỳ file XY nào đã upload.",
                    "Nguồn lỗi": "Tổng hợp các file XY"
                })
            else:
                xy_desc = str(match_xy.iloc[0][col_xy_desc]).strip()
                file_name = match_xy.iloc[0][col_source]
                if bom_desc.lower() != xy_desc.lower():
                    errors.append({
                        "Vị trí": pos,
                        "Loại lỗi": "Sai khác mô tả",
                        "Chi tiết": f"BOM: {bom_desc} | XY: {xy_desc}",
                        "Nguồn lỗi": f"File: {file_name}"
                    })

    # --- CHIỀU 2: KIỂM TRA TỪ XY DATA SANG BOM (Tìm linh kiện thừa) ---
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

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="SMT Advanced Checker", layout="wide")
st.title("Hệ thống đối soát linh
