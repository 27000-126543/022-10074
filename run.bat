@echo off
chcp 65001 >nul
echo ============================================
echo   混凝土浇筑旁站检查工具 - 快速启动脚本
echo ============================================
echo.

if not exist ".venv" (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo 创建虚拟环境失败，请确认已安装Python 3.9+
        pause
        exit /b 1
    )
)

echo [2/3] 激活虚拟环境并安装依赖...
call .venv\Scripts\activate.bat
pip install -e . -q 2>nul

echo.
echo [3/3] 生成示例数据（如果还没有）...
if not exist "示例项目_阳光花园二期" (
    python generate_samples.py
) else (
    echo   示例数据已存在，跳过生成。如需重新生成，请删除该目录。
)

echo.
echo ============================================
echo   准备完成！您现在可以运行以下命令：
echo ============================================
echo.
echo  1. 批量核对（默认检查）：
echo     concrete-inspector check -p 示例项目_阳光花园二期 -s 2024-01-01 -e 2024-01-31
echo.
echo  2. 按严重程度筛选问题：
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --severity high
echo.
echo  3. 按楼栋或监理员筛选：
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --building 3号楼
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --supervisor 张三
echo.
echo  4. 生成整改清单（发给项目部）：
echo     concrete-inspector list -p 示例项目_阳光花园二期 -o ./reports
echo.
echo  5. 查看项目信息（楼栋/监理员列表）：
echo     concrete-inspector info -p 示例项目_阳光花园二期
echo.
echo 提示：输入 concrete-inspector --help 查看完整帮助
echo.
cmd /k
