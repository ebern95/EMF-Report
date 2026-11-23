import streamlit as st
import pandas as pd
import numpy as np
import base64

st.set_page_config(page_title="EMF Report Builder", layout="wide")

# -------------------------------
# Background Image + Styling
# -------------------------------
def add_background(image_file):
    with open(image_file, "rb") as image:
        encoded = base64.b64encode(image.read()).decode()

    st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(
            rgba(255,255,255,0.92),
            rgba(255,255,255,0.92)
        ),
        url("data:image/jpg;base64,{encoded}");
        background-size: 30%;
        background-repeat: no-repeat;
        background-position: right bottom;
    }}

    h1 {{
        color: #1f4e79;
    }}

    .stButton>button {{
        background-color: #1f77b4;
        color: white;
        border-radius: 8px;
        height: 3em;
        font-weight: bold;
    }}

    .stDownloadButton>button {{
        background-color: #2ca02c;
        color: white;
        border-radius: 8px;
        font-weight: bold;
    }}
    </style>
    """, unsafe_allow_html=True)

add_background("EMF.jpg")

# -------------------------------
# Title
# -------------------------------
st.title("📊 EMF Report Builder")

# -------------------------------
# Upload + Guide Layout
# -------------------------------
st.subheader("Upload Required Files")

def upload_with_help(label, help_text):
    col1, col2 = st.columns([3, 1])

    with col1:
        file = st.file_uploader(label, type="csv")

    with col2:
        with st.expander("Guide"):
            st.write(help_text)

    return file

file1 = upload_with_help(
    "Upload EMF SKU List",
    """
    1. Log into PLM
    2. Select tile SKU Dashboard
    3. Paste SKU numbers provided into SKU Number search bar
    4. Click Search and then export file
    5. Make sure to save as.csv file
    """
)

file2 = upload_with_help(
    "Upload EMF Specs",
    """
    1. From EMF SKU List copy all values from Final Product Specification column
    2. Log into PLM
    3. Select tile Specification Property Details
    4. Paste spec list into Specification search bar
    5. For remaining search bars select: ZFINALPRD, ZFIPRODUCT, ZRD_7007 (Packaging Waste Data), ZRD_7007_002 (Consumer & Trade Packaging)
    6. Click Display button then Export to Excel
    7. Download and save as .csv file 

    """
)

file3 = upload_with_help(
    "Upload EMF Logistic",
    """
    1. From EMF SKU List copy all values from Final Product Specification column
    2. Log into PLM
    3. Select tile Specification Property Details
    4. Paste spec list into Specification search bar
    5. For remaining search bars select: ZFINALPRD, ZFIPRODUCT, ZRD_7006 (Logistic Unit), ZRD_7006_001 (All Properties)
    6. Click Display button then Export to Excel
    7. Download and save as .csv file 
    """
)

# -------------------------------
# Processing Function
# -------------------------------
def process_data(df1, df2, df3):

    df1 = df1[['SKU Number','Material Description','Final Product Specification','Brand (Trade Description)']]

    df2 = df2[['Specification','Corrugated','Paperboard','Plastic-Flexible','Plastic-Rigid','Compound - Majority Plastic']]

    df2['Compound - Majority Plastic'] = pd.to_numeric(df2['Compound - Majority Plastic'], errors='coerce')

    df2 = df2[
        (df2['Compound - Majority Plastic'].isna()) |
        (df2['Compound - Majority Plastic'] >= 30)
    ]

    df2 = df2.rename(columns={
        'Specification': 'Final Product Specification',
        'Corrugated': 'CORRUGATED - BOARD',
        'Paperboard': 'PAPERBOARD - NOT LAMINATED',
        'Plastic-Flexible': 'FLEXIBLE - PE',
        'Plastic-Rigid': 'RIGID - PE',
        'Compound - Majority Plastic': 'FLEXIBLE - PP'
    })

    merged = df1.merge(df2, on='Final Product Specification', how='left')

    cols_to_melt = [
        'CORRUGATED - BOARD','PAPERBOARD - NOT LAMINATED',
        'FLEXIBLE - PE','RIGID - PE','FLEXIBLE - PP'
    ]

    merged['_order'] = range(len(merged))

    merged = merged.melt(
        id_vars=[col for col in merged.columns if col not in cols_to_melt],
        value_vars=cols_to_melt,
        var_name='Material & Subclass',
        value_name='Wt/Case(g)'
    )

    merged = merged.dropna(subset=['Wt/Case(g)'])

    merged['Material & Subclass'] = pd.Categorical(
        merged['Material & Subclass'],
        categories=cols_to_melt,
        ordered=True
    )

    merged = merged.sort_values(['_order','Material & Subclass']).drop(columns=['_order'])

    merged['Material & Subclass'] = merged['Material & Subclass'].cat.add_categories(['FLEXIBLE - MULTIMATERIAL'])

    merged.loc[
        (merged['Brand (Trade Description)'] == 'Extra') &
        (merged['Material & Subclass'] == 'FLEXIBLE - PE'),
        'Material & Subclass'
    ] = 'FLEXIBLE - MULTIMATERIAL'

    merged.loc[
        (merged['Material Description'].str.startswith('NG', na=False)) &
        (merged['Material & Subclass'] == 'FLEXIBLE - PE'),
        'Material & Subclass'
    ] = 'FLEXIBLE - MULTIMATERIAL'

    merged.loc[
        (merged['SKU Number'].astype(str).str.startswith(('52','71'))) &
        (merged['Material & Subclass'] == 'FLEXIBLE - PE'),
        'Material & Subclass'
    ] = 'FLEXIBLE - PP'

    eol_map = {
        'CORRUGATED - BOARD': 'RECYCLABLE',
        'FLEXIBLE - PP': 'NOT RECYCLABLE',
        'FLEXIBLE - PE': 'RECYCLE READY',
        'PAPERBOARD - NOT LAMINATED': 'RECYCLABLE',
        'FLEXIBLE - MULTIMATERIAL': 'NOT RECYCLABLE',
        'RIGID - PE': 'NOT RECYCLABLE'
    }

    merged['EOL'] = merged['Material & Subclass'].map(eol_map)

    merged['Item/Case'] = merged['Material Description'].str.extract(r'(\d+)\s*[xX]', expand=False)
    merged['Item/Case'] = pd.to_numeric(merged['Item/Case'], errors='coerce')

    merged.loc[merged['Material & Subclass'] == 'CORRUGATED - BOARD','Item/Case'] = 1

    merged['Wt/Case(g)'] = pd.to_numeric(
        merged['Wt/Case(g)'],
        errors='coerce'
    )

    merged['Item/Case'] = pd.to_numeric(
        merged['Item/Case'],
        errors='coerce'
    )

    merged['Wt/Item (g)'] = (
        merged['Wt/Case(g)'] /
        merged['Item/Case']
    )

    merged['Wt % PCR'] = None

    merged.loc[
        merged['Material & Subclass'] == 'CORRUGATED - BOARD',
        'Wt % PCR'
    ] = 0.98
    merged.loc[
        merged['Material & Subclass'] == 'PAPERBOARD - NOT LAMINATED',
        'Wt % PCR'
    ] = 0.78

    ct_map = {
        'CORRUGATED - BOARD': 'Case',
        'FLEXIBLE - PP': 'Flow Wrap',
        'FLEXIBLE - PE': 'BIB',
        'PAPERBOARD - NOT LAMINATED': 'Carton',
        'FLEXIBLE - MULTIMATERIAL': 'SUP',
        'RIGID - PE': 'Membrane'
    }
    merged['Component Type'] = merged['Material & Subclass'].map(ct_map)

    eu_map = {
        'CORRUGATED - BOARD': 'N/A',
        'FLEXIBLE - PP': 'B2C',
        'FLEXIBLE - PE': 'B2C',
        'PAPERBOARD - NOT LAMINATED': 'N/A',
        'FLEXIBLE - MULTIMATERIAL': 'B2C',
        'RIGID - PE': 'B2C'
    }

    merged['End User'] = merged['Material & Subclass'].map(eu_map)



    has_uk = df3.groupby('Specification')['Pallet Plan ID'].transform(
        lambda x: x.str.contains('UK', na=False).any()
    )

    df3 = df3[
        (has_uk & df3['Pallet Plan ID'].str.contains('UK', na=False)) |
        (~has_uk)
    ]

    df3 = df3.drop_duplicates(subset=['Specification','Trade Unit Per Logistic Unit'])
    df3['Trade Unit Per Logistic Unit'] = pd.to_numeric(
        df3['Trade Unit Per Logistic Unit']
            .astype(str)
            .str.replace(',', '', regex=False)
            .str.strip(),
        errors='coerce'
    )
df3 = df3.dropna(
    subset=['Specification', 'Trade Unit Per Logistic Unit']
)
df3 = df3.loc[df3.groupby('Specification')['Trade Unit Per Logistic Unit'].idxmin()]
    df3 = df3[['Specification','Trade Unit Per Logistic Unit']]
    df3 = df3.rename(columns={'Specification':'Final Product Specification'})

    merged_final = merged.merge(df3, on='Final Product Specification', how='left')

    # Force numeric columns
    merged_final['Wt/Case(g)'] = pd.to_numeric(
        merged_final['Wt/Case(g)'],
        errors='coerce'
    ).astype('float64')

    merged_final['Trade Unit Per Logistic Unit'] = pd.to_numeric(
        merged_final['Trade Unit Per Logistic Unit'],
        errors='coerce'
    ).astype('float64')

    # -------- FIXED SECTION --------
    key_cols = [
        'SKU Number',
        'Material Description',
        'Final Product Specification',
        'Brand (Trade Description)',
        'Trade Unit Per Logistic Unit'
    ]

    merged_final = merged_final.copy()
    merged_final['_order'] = range(len(merged_final))
    merged_final['_type'] = 0

    group_order = (
        merged_final
        .groupby(key_cols, as_index=False, dropna=False)['_order']
        .max()
    )

    extra_rows = group_order[key_cols].copy()

    for col in merged_final.columns:
        if col not in extra_rows.columns:
            extra_rows[col] = None

    extra_rows['_order'] = group_order['_order']
    extra_rows['_type'] = 1

    extra_rows = extra_rows[merged_final.columns]

    merged_final = pd.concat([merged_final, extra_rows], ignore_index=True)

    merged_final = merged_final.sort_values(['_order', '_type'])
    merged_final = merged_final.drop(columns=['_order', '_type']).reset_index(drop=True)

    merged_final['Material & Subclass'] = merged_final['Material & Subclass'].fillna('FLEXIBLE - PE')
    merged_final['Wt/Case(g)'] = merged_final['Wt/Case(g)'].fillna(321.475)
    merged_final['EOL'] = merged_final['EOL'].fillna('RECYCLABLE')

    merged_final['Component Type'] = merged_final['Component Type'].fillna('UL Wrap')
    merged_final['End User'] = merged_final['End User'].fillna('B2B')

    mask = (
        (merged_final['Wt/Case(g)'] == 321.475)
        &
        (merged_final['Trade Unit Per Logistic Unit'].notna())
        &
        (merged_final['Trade Unit Per Logistic Unit'] != 0)
    )

    wt_case = pd.to_numeric(
        merged_final.loc[mask, 'Wt/Case(g)'],
        errors='coerce'
    )

    trade_units = pd.to_numeric(
        merged_final.loc[mask, 'Trade Unit Per Logistic Unit'],
        errors='coerce'
    )

    merged_final.loc[mask, 'Wt/Case(g)'] = (
        wt_case / trade_units
    )
    mask = (
        (merged_final['Component Type'] == 'UL Wrap') &
        (merged_final['Item/Case'].isna())
    )

    merged_final.loc[mask, 'Item/Case'] = (
        merged_final.loc[mask, 'Material Description']
        .str.extract(r'(\d+)\s*[xX]', expand=False)
    )

    merged_final['Item/Case'] = pd.to_numeric(merged_final['Item/Case'], errors='coerce')

    merged_final.loc[
        merged_final['Wt/Item (g)'].isna(),
        'Wt/Item (g)'
    ] = (
        merged_final['Wt/Case(g)'] /
        merged_final['Item/Case']
    )

    size_map = {
        'BIB': 'SMALL',
        'Flow Wrap': 'SMALL',
        'Case': 'N/A',
        'Carton': 'N/A',
        'SUP': 'SMALL',
        'Membrane': 'SMALL',
        'UL Wrap': 'LARGE'
    }

    merged_final['Size'] = merged_final['Component Type'].map(size_map)

    return merged_final


# -------------------------------
# Run Button
# -------------------------------
if st.button("🚀 Run EMF Report"):

    if file1 and file2 and file3:

        def read_csv_safe(uploaded_file):

            encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
            errors = []

            for enc in encodings:
                try:
                    uploaded_file.seek(0)

                    df = pd.read_csv(
                        uploaded_file,
                        encoding=enc,
                        engine="python",
                        on_bad_lines="warn"
                    )

                    df.columns = df.columns.astype(str).str.strip()

                    return df

                except UnicodeDecodeError as e:
                    errors.append(f"{enc}: encoding error")

                except pd.errors.ParserError as e:
                    errors.append(f"{enc}: CSV structure error - {e}")

                except Exception as e:
                    errors.append(f"{enc}: {type(e).__name__} - {e}")

            raise ValueError(
                f"Unable to read {uploaded_file.name}. "
                + " | ".join(errors)
            )

        df1 = read_csv_safe(file1)
        df2 = read_csv_safe(file2)
        df3 = read_csv_safe(file3)


        with st.spinner("Processing data..."):
            result = process_data(df1, df2, df3)

        st.success("Report Generated Successfully ✅")

        st.subheader("📊 Summary Statistics")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Total Rows", len(result))
        col2.metric("Unique SKUs", result['SKU Number'].nunique())
        col3.metric("Total Wt/Case (g)", f"{result['Wt/Case(g)'].sum():,.0f}")
        col4.metric("Total Wt/Item (g)", f"{result['Wt/Item (g)'].sum():,.0f}")

        st.subheader("📦 Material Breakdown")

        material_summary = result.groupby('Material & Subclass').agg(
            Rows=('Material & Subclass','count'),
            Total_Wt=('Wt/Case(g)','sum')
        ).reset_index()

        st.dataframe(material_summary, use_container_width=True)

        st.subheader("🔍 Preview")
        st.dataframe(result.head(50), use_container_width=True)

        csv = result.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="⬇️ Download EMF Report",
            data=csv,
            file_name="EMF_HGM.csv",
            mime="text/csv"
        )

    else:
        st.warning("⚠️ Please upload all three files before running.")
