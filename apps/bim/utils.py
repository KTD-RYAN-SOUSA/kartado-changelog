"""
Utility functions for BIM module.
"""
from django.db import transaction


def delete_bim_model_and_file(bim_model):
    """
    Deleta um modelo BIM e seu arquivo no S3.

    Args:
        bim_model: Instância de BIMModel

    Returns:
        bool: True se deletou com sucesso, False caso contrário
    """
    try:
        # Guarda referência ao arquivo antes de deletar o modelo
        file_field = bim_model.file

        # Se existir arquivo, deletar do S3 explicitamente
        if file_field:
            try:
                # Delete do S3
                file_field.delete(save=False)
            except Exception:
                pass

        # Deletar o registro do banco
        bim_model.delete()

        return True
    except Exception:
        return False


def delete_bim_models_by_company(company):
    """
    Deleta todos os modelos BIM de uma company, incluindo arquivos no S3.

    Otimizado para processar em batches e evitar consumo excessivo de memória.

    Args:
        company: Instância de Company
    """
    from apps.bim.models import BIMModel

    # Usar iterator() para processar em batches e não carregar tudo na memória
    queryset = BIMModel.objects.filter(company=company).iterator(chunk_size=100)

    # Processar em batches dentro de transação
    with transaction.atomic():
        for bim_model in queryset:
            delete_bim_model_and_file(bim_model)
