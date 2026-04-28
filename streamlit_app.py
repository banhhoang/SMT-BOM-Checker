import streamlit as st
import pandas as pd
import io

def full_cross_check(df_bom, df_xy):
    errors = []
    
    # Định nghĩa tên cột
    COL_BOM_DESC = " Mô tả/Yêu cầu kỹ thuật"
    COL_BOM_POS = "Vị trí VTLK"
    COL_BOM_QTY = "Số lượng"
    
    COL_XY_DESIG = "Designator"
    COL_XY_DESC = "Description"

    # Tập hợp tất cả các vị trí được nhắc đến trong BOM để kiểm tra chiều ngược lại
    all_bom_positions = set()

    # --- CHIỀU 1: KIỂM TRA TỪ BOM SANG XY DATA ---
    for _, row in df_bom.iterrows():
        # Bỏ qua dòng trống hoặc dòng tiêu đề nhóm
        if pd.isna(row[COL_BOM_POS]) or str(row[COL_BOM_POS]).strip() == "" or "Tích hợp" in str(row[COL_BOM_POS]):
            continue

        bom_desc = str(row[COL_BOM_DESC]).strip()
        bom_qty = row[COL_BOM_QTY]
        pos_list = [p.strip() for p in str(row[COL_BOM_POS]).replace(';', ',').split(',') if p.strip()]
        
        # Lưu vào tập hợp để đối chiếu chiều ngược lại
        all_bom_positions.update(pos_list)

        # 1.1 Kiểm tra số lượng nội bộ BOM
        if len(pos_list) != bom_qty:
            errors.append({
                "Vị trí/Đối tượng": row[COL_BOM_POS],
                "Loại lỗi": "Sai lệch định mức BOM",
                "Chi tiết": f"BOM ghi SL {bom_qty} nhưng đếm thực tế {len(pos_list)} vị trí."
            })

        # 1.2 Kiểm tra từng vị trí so với XY Data
        for pos in pos_list:
            match_xy = df_xy[df_xy[COL_XY_DESIG] == pos]
            
            if match_xy.empty:
                errors.append({
                    "Vị trí/Đối tượng": pos,
                    "Loại lỗi": "Thiếu trong file XY DATA",
                    "Chi tiết": f"Vị trí {pos} có trong BOM nhưng không tìm thấy trên tọa độ SMT."
                })
            else:
                xy_desc = str(match_xy.iloc[0][COL_XY_DESC]).strip()
                if bom_desc.lower() != xy_desc.lower():
                    errors.append({
                        "Vị trí/Đối tượng": pos,
                        "Loại lỗi": "Sai khác Mô tả (Description)",
                        "Chi tiết": f"BOM: '{bom_desc}' | XY: '{xy_desc}'"
                    })

    # --- CHIỀU 2: KIỂM TRA TỪ XY DATA SANG BOM (Tìm linh kiện thừa) ---
    for _, row in df_xy.iterrows():
        xy_pos = str(row[COL_XY_DESIG]).strip()
        if xy_pos not in all_bom_positions:
            errors.append({
                "Vị trí/Đối tượng": xy_pos,
                "Loại lỗi": "Thừa trong file XY DATA",
                "Chi tiết": f"Vị trí {xy_pos} có trong file tọa độ nhưng không có trong BOM sản xuất."
            })

    return pd.DataFrame(errors)

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="SMT BOM Checker Pro", layout="wide")
st.title("Hệ thống đối soát dữ liệu SMT: BOM vs XY Data")

c1, c2 = st.columns(2)
with c1:
    file_bom = st.file_uploader("1. Upload file BOM", type=['xlsx', 'csv'])
with c2:
    file_xy = st.file_uploader("2. Upload file XY DATA", type=['xlsx', 'csv'])

if file_bom and file_xy:
    try:
        # Đọc dữ liệu
        if file_bom.name.endswith('.csv'): df_bom = pd.read_csv(file_bom)
        else: df_bom = pd.read_excel(file_bom)
        
        if file_xy.name.endswith('.csv'): df_xy = pd.read_csv(file_xy)
        else: df_xy = pd.read_excel(file_xy)
        
        if st.button("🚀 Bắt đầu đối soát 2 chiều"):
            result_df = full_cross_check(df_bom, df_xy)
            
            if result_df.empty:
                st.success("🎉 Tuyệt vời! Hai file hoàn toàn khớp nhau (không thừa, không thiếu, đúng mô tả).")
            else:
                st.warning(f"🚩 Phát hiện {len(result_df)} điểm bất thường.")
                
                # Phân loại lỗi để người dùng dễ quan sát
                st.dataframe(result_df, use_container_width=True)
                
                # Xuất file báo cáo
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result_df.to_excel(writer, index=False, sheet_name='Report')
                
                st.download_button(
                    label="📥 Tải báo cáo lỗi chi tiết",
                    data=output.getvalue(),
                    file_name="Bao_cao_doi_soat_SMT.xlsx",
                    mime="application/vnd.ms-excel"
                )
    except Exception as e:
        st.error(f"Lỗi hệ thống: {e}")
