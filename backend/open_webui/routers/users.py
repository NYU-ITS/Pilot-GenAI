import logging
from typing import Optional

from open_webui.models.auths import Auths
from open_webui.models.chats import Chats
from open_webui.models.users import (
    UserModel,
    UserRoleUpdateForm,
    Users,
    UserSettings,
    UserUpdateForm,
)


from open_webui.socket.main import get_active_status_by_user_id
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from open_webui.utils.auth import get_admin_user, get_password_hash, get_verified_user

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()

############################
# GetUsers
############################


@router.get("/", response_model=list[UserModel])
async def get_users(
    skip: Optional[int] = None,
    limit: Optional[int] = None,
    user=Depends(get_admin_user),
):
    return Users.get_users(skip, limit)


############################
# User Groups
############################


@router.get("/groups")
async def get_user_groups(user=Depends(get_verified_user)):
    return Users.get_user_groups(user.id)


############################
# User Permissions
############################


@router.get("/permissions")
async def get_user_permissisions(user=Depends(get_verified_user)):
    return Users.get_user_groups(user.id)


############################
# User Default Permissions
############################
class WorkspacePermissions(BaseModel):
    models: bool = False
    knowledge: bool = False
    prompts: bool = False
    tools: bool = False


class ChatPermissions(BaseModel):
    controls: bool = True
    file_upload: bool = True
    delete: bool = True
    edit: bool = True
    temporary: bool = True


class FeaturesPermissions(BaseModel):
    web_search: bool = True
    image_generation: bool = True
    code_interpreter: bool = True


class UserPermissions(BaseModel):
    workspace: WorkspacePermissions
    chat: ChatPermissions
    features: FeaturesPermissions


@router.get("/default/permissions", response_model=UserPermissions)
async def get_user_permissions(request: Request, user=Depends(get_admin_user)):
    return {
        "workspace": WorkspacePermissions(
            **request.app.state.config.USER_PERMISSIONS.get("workspace", {})
        ),
        "chat": ChatPermissions(
            **request.app.state.config.USER_PERMISSIONS.get("chat", {})
        ),
        "features": FeaturesPermissions(
            **request.app.state.config.USER_PERMISSIONS.get("features", {})
        ),
    }


@router.post("/default/permissions")
async def update_user_permissions(
    request: Request, form_data: UserPermissions, user=Depends(get_admin_user)
):
    request.app.state.config.USER_PERMISSIONS = form_data.model_dump()
    return request.app.state.config.USER_PERMISSIONS


############################
# UpdateUserRole
############################


# @router.post("/update/role", response_model=Optional[UserModel])
# async def update_user_role(form_data: UserRoleUpdateForm, user=Depends(get_admin_user)):
#     if user.id != form_data.id and form_data.id != Users.get_first_user().id:
#         return Users.update_user_role_by_id(form_data.id, form_data.role)

#     raise HTTPException(
#         status_code=status.HTTP_403_FORBIDDEN,
#         detail=ERROR_MESSAGES.ACTION_PROHIBITED,
#     )


# @router.post("/update/role", response_model=Optional[UserModel])
# async def update_user_role(form_data: UserRoleUpdateForm, user=Depends(get_admin_user)):
#     target_user = Users.get_user_by_id(form_data.id)

#     if not target_user:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

#     # Define a list of allowed emails that can bypass the admin-to-admin restriction.
#     allowed_emails = ["cg4532@nyu.edu"]

#     # Allow the first registered user (super-admin) or allowed emails to change admin roles.
#     if target_user.role == "admin" and not (user.id == Users.get_first_user().id or user.email in allowed_emails):
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Admins cannot change another admin's role",
#         )

#     # Prevent users from changing their own role
#     if user.id == form_data.id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Users cannot change their own role",
#         )

#     # Prevent modifying the role of the first registered user (super-admin)
#     if form_data.id == Users.get_first_user().id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Cannot change the role of the first registered user",
#         )

#     return Users.update_user_role_by_id(form_data.id, form_data.role)


@router.post("/update/role", response_model=Optional[UserModel])
async def update_user_role(form_data: UserRoleUpdateForm, user=Depends(get_admin_user)):
    target_user = Users.get_user_by_id(form_data.id)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Emails that get super-admin-like privileges for admin-to-admin changes.
    allowed_emails = [
        "sm11538@nyu.edu",
        "ms15138@nyu.edu",
        "mb484@nyu.edu",
        "cg4532@nyu.edu",
        "jy4421@nyu.edu",
        "ht2490@nyu.edu",
        "ps5226@nyu.edu",
    ]

    # Prevent users from changing their own role.
    if user.id == form_data.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users cannot change their own role",
        )

    # If the target user is currently an admin,
    # only the super-admin or an allowed email can change that role.
    if target_user.role == "admin" and not (
        user.id == Users.get_first_user().id or user.email in allowed_emails
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change another admin's or super-admin's role",
        )

    # Prevent modifying the role of the first registered user.
    if form_data.id == Users.get_first_user().id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change the role of the first registered user",
        )

    # Now, check if the current user is just a normal admin (not super admin(first user) or not in allowed_emails).
    is_normal_admin = (
        user.role == "admin"
        and user.id != Users.get_first_user().id
        and user.email not in allowed_emails
    )

    # If the user is a normal admin, limit role changes to only "pending" -> "user".
    if is_normal_admin:
        # If requested role is "admin", forbid it.
        if form_data.role == "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin cannot promote a user to admin.",
            )
        # # If requested role is anything other than "user" or "pending", also forbid it.
        # if form_data.role not in ("pending", "user"):
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail="Admins can only change role to 'pending' or 'user'.",
        #     )

    return Users.update_user_role_by_id(form_data.id, form_data.role)


############################
# GetUserSettingsBySessionUser
############################


@router.get("/user/settings", response_model=Optional[UserSettings])
async def get_user_settings_by_session_user(user=Depends(get_verified_user)):
    user = Users.get_user_by_id(user.id)
    if user:
        return user.settings
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.USER_NOT_FOUND,
        )


############################
# UpdateUserSettingsBySessionUser
############################


@router.post("/user/settings/update", response_model=UserSettings)
async def update_user_settings_by_session_user(
    form_data: UserSettings, user=Depends(get_verified_user)
):
    user = Users.update_user_settings_by_id(user.id, form_data.model_dump())
    if user:
        return user.settings
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.USER_NOT_FOUND,
        )


############################
# GetUserInfoBySessionUser
############################


@router.get("/user/info", response_model=Optional[dict])
async def get_user_info_by_session_user(user=Depends(get_verified_user)):
    user = Users.get_user_by_id(user.id)
    if user:
        return user.info
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.USER_NOT_FOUND,
        )


############################
# UpdateUserInfoBySessionUser
############################


@router.post("/user/info/update", response_model=Optional[dict])
async def update_user_info_by_session_user(
    form_data: dict, user=Depends(get_verified_user)
):
    user = Users.get_user_by_id(user.id)
    if user:
        if user.info is None:
            user.info = {}

        user = Users.update_user_by_id(user.id, {"info": {**user.info, **form_data}})
        if user:
            return user.info
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.USER_NOT_FOUND,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.USER_NOT_FOUND,
        )


############################
# GetUserById
############################


class UserResponse(BaseModel):
    name: str
    profile_image_url: str
    active: Optional[bool] = None


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: str, user=Depends(get_verified_user)):
    # Check if user_id is a shared chat
    # If it is, get the user_id from the chat
    if user_id.startswith("shared-"):
        chat_id = user_id.replace("shared-", "")
        chat = Chats.get_chat_by_id(chat_id)
        if chat:
            user_id = chat.user_id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.USER_NOT_FOUND,
            )

    user = Users.get_user_by_id(user_id)

    if user:
        return UserResponse(
            **{
                "name": user.name,
                "profile_image_url": user.profile_image_url,
                "active": get_active_status_by_user_id(user_id),
            }
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.USER_NOT_FOUND,
        )


############################
# UpdateUserById
############################


@router.post("/{user_id}/update", response_model=Optional[UserModel])
async def update_user_by_id(
    user_id: str,
    form_data: UserUpdateForm,
    session_user=Depends(get_admin_user),
):
    user = Users.get_user_by_id(user_id)

    if user:
        if form_data.email.lower() != user.email:
            email_user = Users.get_user_by_email(form_data.email.lower())
            if email_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.EMAIL_TAKEN,
                )

        if form_data.password:
            hashed = get_password_hash(form_data.password)
            log.debug(f"hashed: {hashed}")
            Auths.update_user_password_by_id(user_id, hashed)

        Auths.update_email_by_id(user_id, form_data.email.lower())
        updated_user = Users.update_user_by_id(
            user_id,
            {
                "name": form_data.name,
                "email": form_data.email.lower(),
                "profile_image_url": form_data.profile_image_url,
            },
        )

        if updated_user:
            return updated_user

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.USER_NOT_FOUND,
    )


############################
# DeleteUserById
############################


@router.delete("/{user_id}", response_model=bool)
async def delete_user_by_id(user_id: str, user=Depends(get_admin_user)):
    if user.id != user_id:
        result = Auths.delete_auth_by_id(user_id)

        if result:
            return True

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DELETE_USER_ERROR,
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ERROR_MESSAGES.ACTION_PROHIBITED,
    )
