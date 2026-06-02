@echo off
REM Launch the TEA Tool Streamlit app on Windows
cd /d "%~dp0"
py -3 -m pip install -q -r requirements.txt
py -3 -m streamlit run app.py
