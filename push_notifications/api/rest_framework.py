from __future__ import absolute_import

from rest_framework import permissions
from rest_framework.serializers import ModelSerializer, ValidationError
from rest_framework.viewsets import ModelViewSet
from rest_framework.fields import IntegerField

from push_notifications.models import FCMDevice
from push_notifications.fields import hex_re
from push_notifications.fields import UNSIGNED_64BIT_INT_MAX_VALUE


# Fields


class HexIntegerField(IntegerField):
	"""
	Store an integer represented as a hex string of form "0x01".
	"""

	def to_internal_value(self, data):
		# validate hex string and convert it to the unsigned
		# integer representation for internal use
		try:
			data = int(data, 16) if type(data) != int else data
		except ValueError:
			raise ValidationError("Device ID is not a valid hex number")
		return super(HexIntegerField, self).to_internal_value(data)

	def to_representation(self, value):
		return value


# Serializers
class DeviceSerializerMixin(ModelSerializer):
	class Meta:
		fields = ("id", "name", "registration_id", "device_id", "active", "date_created")
		read_only_fields = ("date_created",)

		# See https://github.com/tomchristie/django-rest-framework/issues/1101
		extra_kwargs = {"active": {"default": True}}


class FCMDeviceSerializer(ModelSerializer):
	device_id = HexIntegerField(
		help_text="ANDROID_ID / TelephonyManager.getDeviceId() (e.g: 0x01)",
		style={"input_type": "text"},
		required=False,
		allow_null=True
	)

	class Meta(DeviceSerializerMixin.Meta):
		model = FCMDevice

		extra_kwargs = {"id": {"read_only": False, "required": False}}

	#def validate_device_id(self, value):
	#	# device ids are 64 bit unsigned values
	#	if value > UNSIGNED_64BIT_INT_MAX_VALUE:
	#		raise ValidationError("Device ID is out of range")
	#	return value

	def validate(self, attrs):
		devices = None
		primary_key = None
		request_method = None

		if self.initial_data.get("registration_id", None):
			if self.instance:
				request_method = "update"
				primary_key = self.instance.id
			else:
				request_method = "create"
		else:
			if self.context["request"].method in ["PUT", "PATCH"]:
				request_method = "update"
				primary_key = attrs["id"]
			elif self.context["request"].method == "POST":
				request_method = "create"

		if request_method == "update":
			devices = FCMDevice.objects.filter(registration_id=attrs["registration_id"]) \
				.exclude(id=primary_key)
		elif request_method == "create":
			devices = FCMDevice.objects.filter(registration_id=attrs["registration_id"])

		if devices:
			raise ValidationError({'registration_id': 'This field must be unique.'})
		return attrs


# Permissions
class IsOwner(permissions.BasePermission):
	def has_object_permission(self, request, view, obj):
		# must be the owner to view the object
		return obj.user == request.user


# Mixins
class DeviceViewSetMixin(object):
	lookup_field = "registration_id"

	def perform_create(self, serializer):
		if self.request.user.is_authenticated():
			serializer.save(user=self.request.user)
		return super(DeviceViewSetMixin, self).perform_create(serializer)

	def perform_update(self, serializer):
		if self.request.user.is_authenticated():
			serializer.save(user=self.request.user)
		return super(DeviceViewSetMixin, self).perform_update(serializer)


class AuthorizedMixin(object):
	permission_classes = (permissions.IsAuthenticated, IsOwner)

	def get_queryset(self):
		# filter all devices to only those belonging to the current user
		return self.queryset.filter(user=self.request.user)


# ViewSets
class FCMDeviceViewSet(DeviceViewSetMixin, ModelViewSet):
	queryset = FCMDevice.objects.all()
	serializer_class = FCMDeviceSerializer


class FCMDeviceAuthorizedViewSet(AuthorizedMixin, FCMDeviceViewSet):
	pass