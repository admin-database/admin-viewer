from admin_viewer.__version__ import __version__
from admin_viewer.update_checker import check_update
from admin_viewer.viewer import ViewerApp

def main():
    app = ViewerApp(__version__)
    app.after(1000, lambda: check_update(app))  # 실행 직후 업데이트 확인
    app.mainloop()

if __name__ == "__main__":
    main()
