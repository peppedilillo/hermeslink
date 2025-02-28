from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser

UserAdmin.fieldsets += (('Gang', {'fields': ('gang',)}),)
UserAdmin.add_fieldsets[0][1]['fields'] += ('gang',)

admin.site.register(CustomUser, UserAdmin)