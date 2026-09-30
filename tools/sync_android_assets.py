from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
source=root/'web-demo';target=root/'android/app/src/main/assets/www'
shutil.copytree(source,target,dirs_exist_ok=True)
print('Copied original-UI web demo into Android assets')
