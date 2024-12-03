from django.db import models

# Create your models here.
class Clause(models.Model):
    identifier = models.CharField(max_length=255, unique=True)  # 조문 식별자
    content = models.TextField()  # 조문 내용

    def __str__(self):
        return self.identifier