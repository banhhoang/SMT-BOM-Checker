import streamlit as st
import pandas as pd
import io

def clean_column_names(df):
    df.columns = [str(col).strip() for col in df.columns]
    return df

def full_cross_check(df_bom, df_xy_combined):
    errors = []
    df_bom = clean_column_names(df_bom)
    df_xy_combined = clean_column_names(df_xy_combined)

    # 1. Xác định các cột trong BOM
    col_bom_desc = next((c for c in df_bom.columns if "Mô tả" in c), None)
    col_bom_pos = next((c for c in df_bom.columns if "Vị trí" in c), None)
    col_bom_qty = next((c for c in df_bom.columns if "Số lượng" in c), None)
    col_bom_hsx = next((c for c in df_bom.columns if "Hãng sản xuất" in c), None)
    col_bom_pn = next((c for c in df_bom.columns if "P/N" in c or "Part Number" in c), None)
    
    # 2. Xác định các cột trong XY Data
    col_xy_desig = next((c for c in df_xy_combined.columns if "Designator" in c), None)
    col_xy_desc = next((c for c in df_xy_combined.columns if "Description" in c), None)
    
    # Tìm tất cả các cột Manufacturer và Part Number trong XY (Manufacturer 1, 2, 3...)
    xy_mfr_cols = sorted([c for c in df_xy_combined.columns if "Manufacturer" in c and "Part Number" not in c])
    xy_pn_cols = sorted([c for c in df_xy_combined.columns if "Manufacturer Part Number" in c or "P/N" in c])
    
    col_source = "File Nguồn"

    if not all([col_bom_desc, col_bom_pos, col_bom_qty, col_xy_desig, col_xy_desc, col_bom_hsx, col_bom_pn]):
        return "Lỗi: Không tìm thấy đủ các cột (Mô tả, Vị trí, Số lượng, Hãng SX, PN) trong file. Vui lòng kiểm tra lại tiêu đề."

    all_bom_positions = {}

    # --- CHIỀU 1: BOM -> XY DATA ---
    for _, row in df_bom.iterrows():
        pos_raw = str(row[col_bom_pos])
        if pd.isna(row[col_bom_pos]) or pos_raw.strip() == "" or "Tích hợp" in pos_raw:
            continue

        bom_desc = str(row[col_bom_desc]).strip()
        bom_hsx = str(row[col_bom_hsx]).strip().lower()
        bom_pn = str(row[col_bom_pn]).strip().lower()
        bom_qty = int(row[col_bom_qty]) if pd.notna(row[col_bom_qty]) else 0
        
        pos_list = [p.strip() for p in pos_raw.replace(';', ',').split(',') if p.strip()]
        for p in pos_list: all_bom_positions[p] = bom_desc

        # Check số lượng
        if len(pos_list) != bom_qty:
            errors.append({"Vị trí": pos_raw, "Loại lỗi": "Sai số lượng BOM", "Chi tiết": f"Ghi {bom_qty} nhưng đếm được {len(pos_list)}", "Nguồn lỗi": "File BOM"})

        for pos in pos_list:
            match_xy = df_xy_combined[df_xy_combined[col_xy_desig] == pos]
            if match_xy.empty:
                errors.append({"Vị trí": pos, "Loại lỗi": "Thiếu trong XY Data", "Chi tiết": "Có trong BOM nhưng không thấy ở file tọa độ nào.", "Nguồn lỗi": "Tổng hợp XY"})
            else:
                xy_row = match_xy.iloc[0]
                file_name = xy_row[col_source]
                
                # Check Mô tả
                xy_desc = str(xy_row[col_xy_desc]).strip()
                if bom_desc.lower() != xy_desc.lower():
                    errors.append({"Vị trí": pos, "Loại lỗi": "Sai mô tả", "Chi tiết": f"BOM: {bom_desc} | XY: {xy_desc}", "Nguồn lỗi": f"File: {file_name}"})

                # --- MỚI: Check Hãng SX và Part Number ---
                found_match = False
                xy_parts_info = [] # Để lưu lại thông tin phục vụ báo lỗi nếu không tìm thấy
                
                # Duyệt qua các cặp Manufacturer và PN trong XY
                for m_col, p_col in zip(xy_mfr_cols, xy_pn_cols):
                    curr_m = str(xy_row[m_col]).strip().lower() if pd.notna(xy_row[m_col]) else ""
                    curr_p = str(xy_row[p_col]).strip().lower() if pd.notna(xy_row[p_col]) else ""
                    
                    if curr_m != "" or curr_p != "":
                        xy_parts_info.append(f"[{curr_m.upper()}: {curr_p.upper()}]")
                    
                    # Nếu khớp cả Hãng và PN (hoặc ít nhất là PN nếu hãng để trống)
                    if bom_pn == curr_p and (bom_hsx in curr_m or curr_m in bom_hsx):
                        found_match = True
                        break
                
                if not found_match:
                    errors.append({
                        "Vị trí": pos,
                        "Loại lỗi": "Sai Hãng SX hoặc P/N",
                        "Chi tiết": f"BOM: {bom_hsx.upper()} - {bom_pn.upper()} | XY hiện có: {', '.join(xy_parts_info)}",
                        "Nguồn lỗi": f"File: {file_name}"
                    })

    # --- CHIỀU 2: XY DATA -> BOM (Thừa) ---
    for _, row in df_xy_combined.iterrows():
        xy_pos = str(row[col_xy_desig]).strip()
        if xy_pos not in all_bom_positions:
            errors.append({"Vị trí": xy_pos, "Loại lỗi": "Thừa trong XY Data", "Chi tiết": "Có tọa độ nhưng không có trong BOM tổng.", "Nguồn lỗi": f"File: {row[col_source]}"})

    return pd.DataFrame(errors)

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="SMT Pro Checker V3", layout="wide")
st.title("Đối soát BOM vs XY Data (Hỗ trợ đa Hãng & đa Mạch)")

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

        if st.button("🚀 Chạy kiểm tra hệ thống"):
            res = full_cross_check(df_bom, df_combined)
            if isinstance(res, str): st.error(res)
            elif res.empty: st.success("✅ Tuyệt vời! Mọi thứ khớp hoàn toàn (Mô tả, Vị trí, Hãng SX, P/N).")
            else:
                st.warning(f"Tìm thấy {len(res)} điểm cần kiểm tra.")
                st.dataframe(res, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as wr: res.to_excel(wr, index=False)
                st.download_button("📥 Tải báo cáo lỗi", out.getvalue(), "Bao_cao_SMT_Chi_tiet.xlsx")
    except Exception as e:
        st.error(f"Lỗi hệ thống: {e}")
