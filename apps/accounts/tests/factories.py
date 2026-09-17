import factory

from apps.accounts.models import Role, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@densourcegroup.ci")
    first_name = "Jean"
    last_name = "Kouassi"
    role = Role.ADMIN
    password = factory.PostGenerationMethodCall("set_password", "Test-Passw0rd!")
