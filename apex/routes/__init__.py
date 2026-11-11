from .auth import bp as auth_bp
from .di import bp as di_bp
from .di_admin import bp as di_admin_bp
from .main import bp as main_bp

__all__ = ["auth_bp", "di_admin_bp", "di_bp", "main_bp"]
