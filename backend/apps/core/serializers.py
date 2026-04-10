"""
النظام الأساسي - Serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Permission, Role, UserProfile

User = get_user_model()


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer للصلاحيات"""
    module_display = serializers.CharField(source='get_module_display', read_only=True)
    
    class Meta:
        model = Permission
        fields = [
            'id', 'code', 'name', 'description', 
            'module', 'module_display', 'is_active', 'created_at'
        ]
        read_only_fields = ['created_at']


class RoleSerializer(serializers.ModelSerializer):
    """Serializer للأدوار"""
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        many=True,
        write_only=True,
        source='permissions',
        required=False
    )
    users_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'description', 'permissions', 
            'permission_ids', 'users_count', 'is_active', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_users_count(self, obj):
        return obj.users.count()


class RoleListSerializer(serializers.ModelSerializer):
    """Serializer مختصر للأدوار"""
    permissions_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'description', 
            'permissions_count', 'users_count', 
            'is_active', 'created_at'
        ]
    
    def get_permissions_count(self, obj):
        return obj.permissions.count()
    
    def get_users_count(self, obj):
        return obj.users.count()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer لملف المستخدم"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.SerializerMethodField()
    role_name = serializers.CharField(source='role.name', read_only=True)
    permissions = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'username', 'email', 
            'first_name', 'last_name', 'full_name',
            'role', 'role_name', 'permissions',
            'phone', 'department', 'position', 'avatar'
        ]
    
    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    
    def get_permissions(self, obj):
        return obj.get_permissions()


class UserSerializer(serializers.ModelSerializer):
    """Serializer للمستخدمين"""
    profile = UserProfileSerializer(read_only=True)
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login',
            'profile', 'role', 'password'
        ]
        read_only_fields = ['date_joined', 'last_login']
    
    def create(self, validated_data):
        role = validated_data.pop('role', None)
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        # إنشاء ملف المستخدم
        UserProfile.objects.create(user=user, role=role)
        return user
    
    def update(self, instance, validated_data):
        role = validated_data.pop('role', None)
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        
        # تحديث الدور في ملف المستخدم
        if role is not None:
            profile, _ = UserProfile.objects.get_or_create(user=instance)
            profile.role = role
            profile.save()
        
        return instance
