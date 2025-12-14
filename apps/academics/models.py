# academics/models.py

from django.db import models
from schoolara.managers import SchoolManager
from utils.models import BaseModel

class AcademicLevel(BaseModel):
    """Model for different academic levels/classes (e.g., Grade 1, Grade 2, Form 1, etc.)"""

    name = models.CharField("Level Name", max_length=50)
    code = models.CharField("Level Code", max_length=10, unique=True)
    description = models.TextField("Description", blank=True)
    
    # Ordering and progression
    order = models.PositiveIntegerField("Order", help_text="For ordering levels")
    next_level = models.ForeignKey(
        'self',
        verbose_name="Next Level",
        on_delete=models.SET_NULL,
        related_name="previous_levels",
        null=True,
        blank=True,
        help_text="The level students progress to after completing this one"
    )
    
    # Section/Stream configuration
    has_sections = models.BooleanField(
        "Has Sections/Streams", 
        default=False,
        help_text="Whether this level has multiple sections/streams (A, B, C, etc.)"
    )
    
    # Status
    is_active = models.BooleanField("Is Active", default=True)
    is_graduation_level = models.BooleanField(
        "Is Graduation Level", 
        default=False,
        help_text="Whether completing this level constitutes graduation"
    )

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return self.name

