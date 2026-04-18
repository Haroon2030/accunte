"""
النظام الأساسي - Serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Permission, Role, UserProfile
from apps.branches.models import Branch

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
    role_type_display = serializers.CharField(source='get_role_type_display', read_only=True)
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'role_type', 'role_type_display', 'description', 'permissions', 
            'permission_ids', 'users_count', 'is_active', 'is_system_role',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_users_count(self, obj):
        return obj.users.count()


class RoleListSerializer(serializers.ModelSerializer):
    """Serializer مختصر للأدوار"""
    permissions_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    role_type_display = serializers.CharField(source='get_role_type_display', read_only=True)
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'role_type', 'role_type_display', 'description', 
            'permissions_count', 'users_count', 
            'is_active', 'is_system_role', 'created_at'
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
    role_type = serializers.CharField(source='role.role_type', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    permissions = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'username', 'email', 
            'first_name', 'last_name', 'full_name',
            'role', 'role_name', 'role_type', 'permissions',
            'branch', 'branch_name',
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
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    password = serializers.CharField(write_only=True, required=False)
    
    # Read-only fields from profile
    role_name = serializers.CharField(source='profile.role.name', read_only=True)
    role_type = serializers.CharField(source='profile.role.role_type', read_only=True)
    branch_id = serializers.IntegerField(source='profile.branch.id', read_only=True)
    branch_name = serializers.CharField(source='profile.branch.name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login',
            'profile', 'role', 'branch', 'password',
            'role_name', 'role_type', 'branch_id', 'branch_name'
        ]
        read_only_fields = ['date_joined', 'last_login']
    
    def create(self, validated_data):
        role = validated_data.pop('role', None)
        branch = validated_data.pop('branch', None)
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        # إنشاء ملف المستخدم مع الفرع
        UserProfile.objects.create(user=user, role=role, branch=branch)
        return user
    
    def update(self, instance, validated_data):
        role = validated_data.pop('role', None)
        branch = validated_data.pop('branch', None)
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        
        # تحديث الدور والفرع في ملف المستخدم
        profile, _ = UserProfile.objects.get_or_create(user=instance)
        if role is not None:
            profile.role = role
        if branch is not None:
            profile.branch = branch
        profile.save()
        
        return instance
