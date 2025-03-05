import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from qcodes import load_by_id   # QCoDeS新版使用 load_by_id 載入實驗數據
import sqlite3
from time import sleep

from qcodes.dataset import initialise_database, load_or_create_experiment
from qcodes.dataset.data_set import load_by_id
import qcodes
import pint

# 初始化 pint 單位
ureg = pint.UnitRegistry()
ureg.formatter.default_format = '~P'  # 使用 SI 前綴格式

class SI:
    """包含 SI 單位的類別，用於格式化數據"""
    A = ureg.ampere
    V = ureg.volt
    Ω = ureg.ohm
    F = ureg.farad
    H = ureg.henry
    W = ureg.watt
    J = ureg.joule
    s = ureg.second
    m = ureg.meter
    g = ureg.gram
    C = ureg.coulomb
    K = ureg.kelvin
    dB = ureg.decibel

    @staticmethod
    def f(value, unit):
        """格式化值並附上適當的 SI 單位"""
        quantity = float(value) * unit
        return f"{quantity.to_compact():.2f~P}"

# 設定 QCoDeS 資料庫路徑，讓 QCoDeS 使用正確的 db 檔案
QCODES_DB_PATH = "/Users/albert-mac/Code/GitHub/QCoDeSStreamlit/020-1Shankar_2024-09-15_01.db"
qcodes.config.core.db_location = QCODES_DB_PATH




def init_database():
    """
    初始化實驗資料庫
    若資料表不存在，則建立 'runs' 表，並以 'id' 作為主鍵
    """
    conn = sqlite3.connect(QCODES_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS runs
                 (id INTEGER PRIMARY KEY, 
                  timestamp DATETIME,
                  parameters TEXT,
                  data BLOB)''')
    conn.commit()
    conn.close()

@st.cache_data(ttl=300)
def fetch_live_data(last_index=0):
    """
    從自訂資料庫中實時取得新增的實驗描述數據
    此函數根據 'id' 欄位（主鍵）查詢大於 last_index 的資料
    回傳的 DataFrame 主要包含實驗描述資訊，若有需要請改為查詢測量結果資料表
    """
    conn = sqlite3.connect(DB_PATH)
    # 注意：資料表中主鍵欄位名稱為 'id'，故 SQL 查詢應使用 id > {last_index}
    query = f"SELECT * FROM runs WHERE id > {last_index}"
    new_data = pd.read_sql(query, conn)
    conn.close()
    # 若有新數據，則取最新的 'id' 作為 last_index
    return new_data, new_data['id'].max() if not new_data.empty else last_index

def realtime_plotting():
    """
    實時繪圖核心函數
    此函數會持續從資料庫讀取新增的實驗描述數據，
    並依據使用者所選的繪圖類型動態更新圖表
    ※ 注意：此範例假設資料庫中已儲存測量結果欄位，例如 'voltage', 'current' 等，
    如無此欄位請根據實際情況調整 SQL 查詢與繪圖參數
    """
    st.title("QCoDeS實驗數據實時監控平台")
    
    # 建立控制面板與繪圖區域的版面分割
    control_col, plot_col = st.columns([1, 3])
    
    with control_col:
        st.header("控制面板")
        update_interval = st.slider("更新間隔(秒)", 0.1, 5.0, 1.0)
        plot_type = st.selectbox(
            "繪圖類型",
            ["散點圖", "線圖", "表面圖", "直方圖"]
        )
    
    with plot_col:
        st.header("實時數據可視化")
        plot_placeholder = st.empty()
        
        last_index = 0
        # 持續輪詢並更新圖表
        while True:
            new_data, last_index = fetch_live_data(last_index)
            if not new_data.empty:
                fig = create_plot(new_data, plot_type)
                plot_placeholder.plotly_chart(fig, use_container_width=True)
            sleep(update_interval)

def create_plot(data, plot_type):
    """
    根據不同的繪圖類型建立交互式 Plotly 圖表
    此處假設 data DataFrame 中包含 'voltage', 'current', 'temperature', 'frequency' 等欄位
    ※ 若資料庫中存放的欄位名稱不同，請相應調整此處參數
    """
    if plot_type == "散點圖":
        fig = px.scatter(data, x='voltage', y='current', 
                         color='temperature',
                         hover_data=['frequency'])
    elif plot_type == "線圖":
        fig = px.line(data, x='time', y='current', 
                      line_group='id',
                      color='parameters')
    elif plot_type == "表面圖":
        fig = go.Figure(data=[go.Surface(z=data[['voltage', 'current', 'temperature']].values)])
    elif plot_type == "直方圖":
        fig = px.histogram(data, x='current', nbins=50)
    
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=30, b=0)
    )
    return fig

        
# def qcodes_integration():
    """
    QCoDeS集成模組
    此模組提供 QCoDeS 數據載入介面，使用者可在側邊欄輸入實驗 ID，
    並透過 QCoDeS API 載入完整的實驗數據，進而利用 get_parameter_data() 動態取得資料庫中
    的測量參數名稱，提高在不同儀器配置下的泛用性。
    """
    st.sidebar.header("QCoDeS 控制接口")
    
    # 初始化 QCoDeS 資料庫（如果不存在則建立）
    initialise_database()
    
    run_id = st.sidebar.number_input("輸入實驗 ID", value=1, step=1)
    
    if st.sidebar.button("載入實驗數據"):
        try:
            dataset = load_by_id(run_id)  # 確保載入 QCoDeS 內的 run_id
            param_data = dataset.get_parameter_data()
            # 動態取得所有可用的參數名稱
            available_params = list(param_data.keys())
            st.sidebar.write("可用參數：", available_params)
            # 此處示範：假設使用者希望繪製 'voltage' 與 'current' 的數據
            # 若資料庫中找不到 'voltage' 或 'current'，則提示使用者
            if 'voltage' in available_params and 'current' in available_params:
                # 由 get_parameter_data() 回傳的數據結構為：{ param_name: { param_name: array, setpoint1: array, ... } }
                # 此處簡單地取出各自的主數據（以相同鍵名存放）
                df = pd.DataFrame({
                    'voltage': param_data['voltage'].get('voltage'),
                    'current': param_data['current'].get('current')
                })
                st.session_state.current_data = df
            else:
                st.warning("找不到 'voltage' 或 'current' 參數，請檢查數據庫內容！")
        
        except ValueError as e:
            st.error(f"載入實驗數據失敗：{e}")

    if 'current_data' in st.session_state:
        st.dataframe(st.session_state.current_data)
        

# def qcodes_integration():
#     """QCoDeS 集成模組，允許用戶選擇參數並可視化數據"""
#     st.sidebar.header("QCoDeS 控制接口")
#     run_id = st.sidebar.number_input("輸入實驗 ID", value=1, step=1)

#     if st.sidebar.button("載入實驗數據"):
#         dataset = load_by_id(run_id)
#         df = dataset.to_pandas_dataframe().reset_index()  # 轉換數據並重設索引
#         parameters = dataset.parameters.split(",")  # 取得所有可用參數
#         st.session_state["df"] = df
#         st.session_state["parameters"] = parameters

#     if "df" in st.session_state and "parameters" in st.session_state:
#         df = st.session_state["df"]
#         parameters = st.session_state["parameters"]

#         st.sidebar.write(f"可用參數：{parameters}")

#         x_param = st.sidebar.selectbox("選擇 X 軸變數", parameters, index=0)
#         y_param = st.sidebar.selectbox("選擇 Y 軸變數", parameters, index=1 if len(parameters) > 1 else 0)

#         if x_param and y_param:
#             fig = px.line(df, x=x_param, y=y_param, labels={x_param: x_param, y_param: y_param})
#             st.plotly_chart(fig, use_container_width=True)
            
            

import plotly.express as px

def qcodes_integration():
    """QCoDeS 整合模組，允許用戶選擇參數並可視化數據（折線圖或熱力圖）"""
    st.sidebar.header("QCoDeS 控制接口")
    run_id = st.sidebar.number_input("輸入實驗 ID", value=1, step=1)

    if st.sidebar.button("載入實驗數據"):
        dataset = load_by_id(run_id)
        df = dataset.to_pandas_dataframe().reset_index()  # 轉換數據並重設索引
        parameters = dataset.parameters.split(",")  # 取得所有可用參數
        st.session_state["df"] = df
        st.session_state["parameters"] = parameters

    if "df" in st.session_state and "parameters" in st.session_state:
        df = st.session_state["df"]
        parameters = st.session_state["parameters"]

        st.sidebar.write(f"可用參數：{parameters}")

        # 讓使用者選擇圖表類型
        chart_type = st.sidebar.radio("選擇圖表類型", ["折線圖", "熱力圖"])

        if chart_type == "折線圖":
            x_param = st.sidebar.selectbox("選擇 X 軸變數", parameters, index=0)
            y_param = st.sidebar.selectbox("選擇 Y 軸變數", parameters, index=1 if len(parameters) > 1 else 0)

            if x_param and y_param:
                fig = px.line(df, x=x_param, y=y_param, labels={x_param: x_param, y_param: y_param})
                st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "熱力圖":
            x_param = st.sidebar.selectbox("選擇 X 軸變數", parameters, index=0)
            y_param = st.sidebar.selectbox("選擇 Y 軸變數", parameters, index=1 if len(parameters) > 1 else 0)
            color_param = st.sidebar.selectbox("選擇顏色對應變數", parameters, index=2 if len(parameters) > 2 else 0)

            if x_param and y_param and color_param:
                fig = px.scatter(df, x=x_param, y=y_param, color=df[color_param], 
                                 labels={x_param: x_param, y_param: y_param, color_param: color_param}, 
                                 color_continuous_scale="Viridis")  # 選擇熱力圖配色
                st.plotly_chart(fig, use_container_width=True)



    # **顯示數據表與圖表**
    if "current_data" in st.session_state and st.session_state.current_data is not None:
        st.dataframe(st.session_state.current_data)
        st.line_chart(st.session_state.current_data.set_index(x_param))  # 以 X 軸作為索引繪圖





# 主程式進入點
if __name__ == "__main__":
    init_database()          # 初始化自訂資料庫
    # 選擇運行方式：
    # 若要運行實時繪圖功能，請取消下面 realtime_plotting() 的註解
    # 若要使用 QCoDeS 數據載入及參數展示功能，請運行 qcodes_integration()
    # 由於 realtime_plotting() 為無窮迴圈，兩者建議分別測試
    # realtime_plotting()
    qcodes_integration()
