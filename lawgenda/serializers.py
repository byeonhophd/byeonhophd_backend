# serializers.py

from rest_framework import serializers
from .models import Clause

class ClauseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clause
        fields = ['identifier', 'content']