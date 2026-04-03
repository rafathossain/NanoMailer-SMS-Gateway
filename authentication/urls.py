from django.urls import path
from . import views

urlpatterns = [
    path('auth/sign-in', views.signin_view, name='signin'),
    path('auth/sign-up', views.signup_view, name='signup'),
    path('auth/verify-otp', views.verify_otp_view, name='verify_otp'),
    path('auth/logout', views.logout_view, name='logout'),
]
