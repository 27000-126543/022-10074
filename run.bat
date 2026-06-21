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
echo  【初始化】生成项目自定义规则配置文件：
echo     concrete-inspector init-rules -o 我的项目_rules.json
echo     （编辑后放到项目目录，check/filter/list 会自动加载）
echo.
echo  1. 批量核对（推荐首次用 --format all，同时导出TXT/Excel/CSV）：
echo     concrete-inspector check -p 示例项目_阳光花园二期 -s 2024-01-01 -e 2024-01-31 --format all -o ./reports
echo     concrete-inspector check -p 示例项目_阳光花园二期 --rules 我的项目_rules.json
echo.
echo  2. 按条件筛选问题：
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --severity high
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --building 3号楼
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --supervisor 张三
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --consistency-only   (只看资料不一致)
echo     concrete-inspector filter -p 示例项目_阳光花园二期 --issue-type missing_photo --issue-type missing_sign
echo.
echo  3. 生成整改清单（发项目部，默认同时导出CSV带回填列）：
echo     concrete-inspector list -p 示例项目_阳光花园二期 -o ./reports --format all
echo     concrete-inspector list -p 示例项目_阳光花园二期 --format csv   (仅导出CSV)
echo     concrete-inspector list -p 示例项目_阳光花园二期 --building 1号楼
echo.
echo  4. 查看项目信息和规则详情：
echo     concrete-inspector info -p 示例项目_阳光花园二期
echo.
echo  5. 每周抽查汇总周报（给领导看，按楼栋/监理员/责任岗位统计）：
echo     concrete-inspector weekly -p 示例项目_阳光花园二期 -s 2024-01-01 -e 2024-01-31 --format all -o ./reports
echo     concrete-inspector weekly -p 示例项目_阳光花园二期 --format excel
echo     concrete-inspector weekly -p 示例项目_阳光花园二期 -i 上周整改清单.csv   ^(导入上周CSV看闭环看板^)
echo.
echo  6. 问题跟踪（导入上周整改CSV，识别已整改/新增/仍未整改）：
echo     concrete-inspector track -p 示例项目_阳光花园二期 -i 上周整改清单.csv --format all -o ./reports
echo.
echo  7. 历史趋势（查看最近几周的合格率、问题类型、关闭率变化）：
echo     concrete-inspector trend -p 示例项目_阳光花园二期 -n 8
echo     concrete-inspector trend -p 示例项目_阳光花园二期 --format csv -o ./reports
echo.
echo  8. 滚动整改清单（导出时合并上周回填，项目部继续填写）：
echo     concrete-inspector list -p 示例项目_阳光花园二期 -i 上周整改清单.csv --format csv -o ./reports
echo.
echo  9. 按日期严格过滤（按最终识别的浇筑日期，范围外不混入）：
echo     concrete-inspector check -p 示例项目_阳光花园二期 -s 2024-01-10 -e 2024-01-20
echo.
echo 提示：输入 concrete-inspector --help 或 concrete-inspector check --help 查看完整帮助
echo.
cmd /k
