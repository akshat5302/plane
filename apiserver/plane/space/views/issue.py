# Python imports
import json

# Django imports
from django.utils import timezone
from django.db.models import (
    Prefetch,
    OuterRef,
    Func,
    F,
    Q,
    Case,
    Value,
    CharField,
    When,
    Exists,
    Max,
    IntegerField,
)
from django.core.serializers.json import DjangoJSONEncoder

# Third Party imports
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

# Module imports
from .base import BaseViewSet, BaseAPIView
from plane.app.serializers import (
    IssueCommentSerializer,
    IssueReactionSerializer,
    CommentReactionSerializer,
    IssueVoteSerializer,
    IssuePublicSerializer,
)

from plane.db.models import (
    Issue,
    IssueComment,
    Label,
    IssueLink,
    IssueAttachment,
    State,
    ProjectMember,
    IssueReaction,
    CommentReaction,
    ProjectDeployBoard,
    IssueVote,
    ProjectPublicMember,
)
from plane.utils.grouper import (
    issue_queryset_grouper,
    issue_on_results,
)
from plane.bgtasks.issue_activites_task import issue_activity
from plane.utils.issue_filters import issue_filters
from plane.utils.order_queryset import order_issue_queryset
from plane.utils.paginator import GroupedOffsetPaginator

class IssueCommentPublicViewSet(BaseViewSet):
    serializer_class = IssueCommentSerializer
    model = IssueComment

    filterset_fields = [
        "issue__id",
        "workspace__id",
    ]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            self.permission_classes = [
                AllowAny,
            ]
        else:
            self.permission_classes = [
                IsAuthenticated,
            ]

        return super(IssueCommentPublicViewSet, self).get_permissions()

    def get_queryset(self):
        try:
            project_deploy_board = ProjectDeployBoard.objects.get(
                workspace__slug=self.kwargs.get("slug"),
                project_id=self.kwargs.get("project_id"),
            )
            if project_deploy_board.comments:
                return self.filter_queryset(
                    super()
                    .get_queryset()
                    .filter(workspace__slug=self.kwargs.get("slug"))
                    .filter(issue_id=self.kwargs.get("issue_id"))
                    .filter(access="EXTERNAL")
                    .select_related("project")
                    .select_related("workspace")
                    .select_related("issue")
                    .annotate(
                        is_member=Exists(
                            ProjectMember.objects.filter(
                                workspace__slug=self.kwargs.get("slug"),
                                project_id=self.kwargs.get("project_id"),
                                member_id=self.request.user.id,
                                is_active=True,
                            )
                        )
                    )
                    .distinct()
                ).order_by("created_at")
            return IssueComment.objects.none()
        except ProjectDeployBoard.DoesNotExist:
            return IssueComment.objects.none()

    def create(self, request, slug, project_id, issue_id):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )

        if not project_deploy_board.comments:
            return Response(
                {"error": "Comments are not enabled for this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = IssueCommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                issue_id=issue_id,
                actor=request.user,
                access="EXTERNAL",
            )
            issue_activity.delay(
                type="comment.activity.created",
                requested_data=json.dumps(
                    serializer.data, cls=DjangoJSONEncoder
                ),
                actor_id=str(request.user.id),
                issue_id=str(issue_id),
                project_id=str(project_id),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
            )
            if not ProjectMember.objects.filter(
                project_id=project_id,
                member=request.user,
                is_active=True,
            ).exists():
                # Add the user for workspace tracking
                _ = ProjectPublicMember.objects.get_or_create(
                    project_id=project_id,
                    member=request.user,
                )

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, slug, project_id, issue_id, pk):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )

        if not project_deploy_board.comments:
            return Response(
                {"error": "Comments are not enabled for this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comment = IssueComment.objects.get(
            workspace__slug=slug, pk=pk, actor=request.user
        )
        serializer = IssueCommentSerializer(
            comment, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            issue_activity.delay(
                type="comment.activity.updated",
                requested_data=json.dumps(request.data, cls=DjangoJSONEncoder),
                actor_id=str(request.user.id),
                issue_id=str(issue_id),
                project_id=str(project_id),
                current_instance=json.dumps(
                    IssueCommentSerializer(comment).data,
                    cls=DjangoJSONEncoder,
                ),
                epoch=int(timezone.now().timestamp()),
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, slug, project_id, issue_id, pk):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )

        if not project_deploy_board.comments:
            return Response(
                {"error": "Comments are not enabled for this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comment = IssueComment.objects.get(
            workspace__slug=slug,
            pk=pk,
            project_id=project_id,
            actor=request.user,
        )
        issue_activity.delay(
            type="comment.activity.deleted",
            requested_data=json.dumps({"comment_id": str(pk)}),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=json.dumps(
                IssueCommentSerializer(comment).data,
                cls=DjangoJSONEncoder,
            ),
            epoch=int(timezone.now().timestamp()),
        )
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueReactionPublicViewSet(BaseViewSet):
    serializer_class = IssueReactionSerializer
    model = IssueReaction

    def get_queryset(self):
        try:
            project_deploy_board = ProjectDeployBoard.objects.get(
                workspace__slug=self.kwargs.get("slug"),
                project_id=self.kwargs.get("project_id"),
            )
            if project_deploy_board.reactions:
                return (
                    super()
                    .get_queryset()
                    .filter(workspace__slug=self.kwargs.get("slug"))
                    .filter(project_id=self.kwargs.get("project_id"))
                    .filter(issue_id=self.kwargs.get("issue_id"))
                    .order_by("-created_at")
                    .distinct()
                )
            return IssueReaction.objects.none()
        except ProjectDeployBoard.DoesNotExist:
            return IssueReaction.objects.none()

    def create(self, request, slug, project_id, issue_id):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )

        if not project_deploy_board.reactions:
            return Response(
                {"error": "Reactions are not enabled for this project board"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = IssueReactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id, issue_id=issue_id, actor=request.user
            )
            if not ProjectMember.objects.filter(
                project_id=project_id,
                member=request.user,
                is_active=True,
            ).exists():
                # Add the user for workspace tracking
                _ = ProjectPublicMember.objects.get_or_create(
                    project_id=project_id,
                    member=request.user,
                )
            issue_activity.delay(
                type="issue_reaction.activity.created",
                requested_data=json.dumps(
                    self.request.data, cls=DjangoJSONEncoder
                ),
                actor_id=str(self.request.user.id),
                issue_id=str(self.kwargs.get("issue_id", None)),
                project_id=str(self.kwargs.get("project_id", None)),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, slug, project_id, issue_id, reaction_code):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )

        if not project_deploy_board.reactions:
            return Response(
                {"error": "Reactions are not enabled for this project board"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        issue_reaction = IssueReaction.objects.get(
            workspace__slug=slug,
            issue_id=issue_id,
            reaction=reaction_code,
            actor=request.user,
        )
        issue_activity.delay(
            type="issue_reaction.activity.deleted",
            requested_data=None,
            actor_id=str(self.request.user.id),
            issue_id=str(self.kwargs.get("issue_id", None)),
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=json.dumps(
                {
                    "reaction": str(reaction_code),
                    "identifier": str(issue_reaction.id),
                }
            ),
            epoch=int(timezone.now().timestamp()),
        )
        issue_reaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentReactionPublicViewSet(BaseViewSet):
    serializer_class = CommentReactionSerializer
    model = CommentReaction

    def get_queryset(self):
        try:
            project_deploy_board = ProjectDeployBoard.objects.get(
                workspace__slug=self.kwargs.get("slug"),
                project_id=self.kwargs.get("project_id"),
            )
            if project_deploy_board.reactions:
                return (
                    super()
                    .get_queryset()
                    .filter(workspace__slug=self.kwargs.get("slug"))
                    .filter(project_id=self.kwargs.get("project_id"))
                    .filter(comment_id=self.kwargs.get("comment_id"))
                    .order_by("-created_at")
                    .distinct()
                )
            return CommentReaction.objects.none()
        except ProjectDeployBoard.DoesNotExist:
            return CommentReaction.objects.none()

    def create(self, request, slug, project_id, comment_id):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )

        if not project_deploy_board.reactions:
            return Response(
                {"error": "Reactions are not enabled for this board"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CommentReactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                comment_id=comment_id,
                actor=request.user,
            )
            if not ProjectMember.objects.filter(
                project_id=project_id,
                member=request.user,
                is_active=True,
            ).exists():
                # Add the user for workspace tracking
                _ = ProjectPublicMember.objects.get_or_create(
                    project_id=project_id,
                    member=request.user,
                )
            issue_activity.delay(
                type="comment_reaction.activity.created",
                requested_data=json.dumps(
                    self.request.data, cls=DjangoJSONEncoder
                ),
                actor_id=str(self.request.user.id),
                issue_id=None,
                project_id=str(self.kwargs.get("project_id", None)),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, slug, project_id, comment_id, reaction_code):
        project_deploy_board = ProjectDeployBoard.objects.get(
            workspace__slug=slug, project_id=project_id
        )
        if not project_deploy_board.reactions:
            return Response(
                {"error": "Reactions are not enabled for this board"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment_reaction = CommentReaction.objects.get(
            project_id=project_id,
            workspace__slug=slug,
            comment_id=comment_id,
            reaction=reaction_code,
            actor=request.user,
        )
        issue_activity.delay(
            type="comment_reaction.activity.deleted",
            requested_data=None,
            actor_id=str(self.request.user.id),
            issue_id=None,
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=json.dumps(
                {
                    "reaction": str(reaction_code),
                    "identifier": str(comment_reaction.id),
                    "comment_id": str(comment_id),
                }
            ),
            epoch=int(timezone.now().timestamp()),
        )
        comment_reaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueVotePublicViewSet(BaseViewSet):
    model = IssueVote
    serializer_class = IssueVoteSerializer

    def get_queryset(self):
        try:
            project_deploy_board = ProjectDeployBoard.objects.get(
                workspace__slug=self.kwargs.get("slug"),
                project_id=self.kwargs.get("project_id"),
            )
            if project_deploy_board.votes:
                return (
                    super()
                    .get_queryset()
                    .filter(issue_id=self.kwargs.get("issue_id"))
                    .filter(workspace__slug=self.kwargs.get("slug"))
                    .filter(project_id=self.kwargs.get("project_id"))
                )
            return IssueVote.objects.none()
        except ProjectDeployBoard.DoesNotExist:
            return IssueVote.objects.none()

    def create(self, request, slug, project_id, issue_id):
        issue_vote, _ = IssueVote.objects.get_or_create(
            actor_id=request.user.id,
            project_id=project_id,
            issue_id=issue_id,
        )
        # Add the user for workspace tracking
        if not ProjectMember.objects.filter(
            project_id=project_id,
            member=request.user,
            is_active=True,
        ).exists():
            _ = ProjectPublicMember.objects.get_or_create(
                project_id=project_id,
                member=request.user,
            )
        issue_vote.vote = request.data.get("vote", 1)
        issue_vote.save()
        issue_activity.delay(
            type="issue_vote.activity.created",
            requested_data=json.dumps(
                self.request.data, cls=DjangoJSONEncoder
            ),
            actor_id=str(self.request.user.id),
            issue_id=str(self.kwargs.get("issue_id", None)),
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
        )
        serializer = IssueVoteSerializer(issue_vote)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, slug, project_id, issue_id):
        issue_vote = IssueVote.objects.get(
            workspace__slug=slug,
            project_id=project_id,
            issue_id=issue_id,
            actor_id=request.user.id,
        )
        issue_activity.delay(
            type="issue_vote.activity.deleted",
            requested_data=None,
            actor_id=str(self.request.user.id),
            issue_id=str(self.kwargs.get("issue_id", None)),
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=json.dumps(
                {
                    "vote": str(issue_vote.vote),
                    "identifier": str(issue_vote.id),
                }
            ),
            epoch=int(timezone.now().timestamp()),
        )
        issue_vote.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueRetrievePublicEndpoint(BaseAPIView):
    permission_classes = [
        AllowAny,
    ]

    def get(self, request, slug, project_id, issue_id):
        issue = Issue.objects.get(
            workspace__slug=slug, project_id=project_id, pk=issue_id
        )
        serializer = IssuePublicSerializer(issue)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProjectIssuesPublicEndpoint(BaseAPIView):
    permission_classes = [
        AllowAny,
    ]

    def get(self, request, slug, project_id):
        if not ProjectDeployBoard.objects.filter(
            workspace__slug=slug, project_id=project_id
        ).exists():
            return Response(
                {"error": "Project is not published"},
                status=status.HTTP_404_NOT_FOUND,
            )

        filters = issue_filters(request.query_params, "GET")

        order_by_param = request.GET.get("order_by", "-created_at")

        issue_queryset = (
            Issue.objects.filter(project_id=self.kwargs.get("project_id"))
            .filter(workspace__slug=self.kwargs.get("slug"))
            .filter(is_draft=True)
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module")
            .annotate(cycle_id=F("issue_cycle__cycle_id"))
            .annotate(
                link_count=IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                attachment_count=IssueAttachment.objects.filter(
                    issue=OuterRef("id")
                )
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                sub_issues_count=Issue.issue_objects.filter(
                    parent=OuterRef("id")
                )
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
        ).distinct()

        order_by_param = request.GET.get("order_by", "-created_at")

        issue_queryset = self.get_queryset().filter(**filters)

        # Issue queryset
        issue_queryset = order_issue_queryset(
            issue_queryset=issue_queryset,
            order_by_param=order_by_param,
        )

        # Group by
        group_by = request.GET.get("group_by", False)
        issue_queryset = issue_queryset_grouper(
            queryset=issue_queryset, field=group_by
        )

        # List Paginate
        if not group_by:
            return self.paginate(
                request=request,
                queryset=issue_queryset,
                on_results=lambda issues: issue_on_results(
                    group_by=group_by, issues=issues
                ),
            )

        # Group paginate
        return self.paginate(
            request=request,
            queryset=issue_queryset,
            on_results=lambda issues: issue_on_results(
                group_by=group_by, issues=issues
            ),
            paginator_cls=GroupedOffsetPaginator,
            group_by_field_name=group_by,
            count_filter=Q(
                Q(issue_inbox__status=1)
                | Q(issue_inbox__status=-1)
                | Q(issue_inbox__status=2)
                | Q(issue_inbox__isnull=True),
                archived_at__isnull=False,
                is_draft=True,
            ),
        )
