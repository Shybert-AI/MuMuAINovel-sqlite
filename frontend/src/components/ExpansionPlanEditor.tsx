import { Modal, Form, Input, InputNumber, Select, Tag, Space, Button, message, Divider } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useState, useEffect, useCallback } from 'react';
import type { ExpansionPlanData, Character } from '../types';
import { characterApi } from '../services/api';

const { TextArea } = Input;

interface ExpansionPlanEditorProps {
  visible: boolean;
  planData: ExpansionPlanData | null;
  chapterSummary: string | null;
  projectId: string;
  onSave: (data: ExpansionPlanData & { summary?: string }) => Promise<void>;
  onCancel: () => void;
}

export default function ExpansionPlanEditor({
  visible,
  planData,
  chapterSummary,
  projectId,
  onSave,
  onCancel
}: ExpansionPlanEditorProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  
  // 关键事件标签输入
  const [keyEventInput, setKeyEventInput] = useState('');
  const [keyEvents, setKeyEvents] = useState<string[]>([]);
  
  // 角色列表和选择
  const [availableCharacters, setAvailableCharacters] = useState<Character[]>([]);
  const [characters, setCharacters] = useState<string[]>([]);
  const [loadingCharacters, setLoadingCharacters] = useState(false);

  // 加载项目角色列表
  const loadCharacters = useCallback(async () => {
    try {
      setLoadingCharacters(true);
      setAvailableCharacters([]); // 重置为空数组
      const response = await characterApi.getCharacters(projectId);
      console.log('加载到的角色数据:', response);
      
      // API返回的是 {total, items} 格式,需要提取items
      let chars: Character[] = [];
      if (Array.isArray(response)) {
        chars = response;
      } else if (response && typeof response === 'object' && 'items' in response) {
        const responseObj = response as { items?: Character[] };
        if (Array.isArray(responseObj.items)) {
          chars = responseObj.items;
        }
      } else {
        console.error('角色API返回格式异常:', response);
        message.warning('角色数据格式异常');
      }
      
      setAvailableCharacters(chars);
      console.log('设置的角色列表:', chars);
    } catch (error: unknown) {
      console.error('加载角色列表失败:', error);
      setAvailableCharacters([]);
      const err = error as Error;
      message.error('加载角色列表失败: ' + (err?.message || '未知错误'));
    } finally {
      setLoadingCharacters(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (visible && projectId) {
      loadCharacters();
    }
  }, [visible, projectId, loadCharacters]);

  // 当planData或chapterSummary变化时更新状态
  useEffect(() => {
    if (visible) {
      if (planData) {
        setKeyEvents(planData.key_events || []);
        setCharacters(planData.character_focus || []);
        form.setFieldsValue({
          summary: chapterSummary || '',
          emotional_tone: planData.emotional_tone,
          narrative_goal: planData.narrative_goal,
          conflict_type: planData.conflict_type,
          estimated_words: planData.estimated_words
        });
      } else {
        // 重置状态
        setKeyEvents([]);
        setCharacters([]);
        form.setFieldsValue({
          summary: chapterSummary || ''
        });
      }
    }
  }, [planData, chapterSummary, form, visible]);

  const handleAddKeyEvent = () => {
    if (keyEventInput.trim()) {
      setKeyEvents([...keyEvents, keyEventInput.trim()]);
      setKeyEventInput('');
    }
  };

  const handleAddCharacter = (characterName: string) => {
    if (characterName && !characters.includes(characterName)) {
      setCharacters([...characters, characterName]);
    }
  };

  const handleSubmit = async () => {
    try {
      setLoading(true);
      const values = await form.validateFields();
      
      // 验证至少有一个关键事件
      if (keyEvents.length === 0) {
        message.warning('请至少添加一个关键事件');
        setLoading(false);
        return;
      }
      
      // 验证至少有一个角色
      if (characters.length === 0) {
        message.warning('请至少添加一个涉及角色');
        setLoading(false);
        return;
      }
      
      const updatedPlan: ExpansionPlanData & { summary?: string } = {
        summary: values.summary,
        key_events: keyEvents,
        character_focus: characters,
        emotional_tone: values.emotional_tone,
        narrative_goal: values.narrative_goal,
        conflict_type: values.conflict_type,
        estimated_words: values.estimated_words,
        scenes: planData?.scenes || null
      };
      
      await onSave(updatedPlan);
      // message.success('规划信息保存成功');
    } catch (error) {
      console.error('保存失败:', error);
      message.error('保存失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setKeyEvents([]);
    setCharacters([]);
    setKeyEventInput('');
    onCancel();
  };

  return (
    <Modal
      title="编辑章节规划"
      open={visible}
      onCancel={handleCancel}
      width={700}
      centered
      footer={[
        <Button key="cancel" onClick={handleCancel} disabled={loading}>
          取消
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          保存
        </Button>
      ]}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          emotional_tone: '紧张激烈',
          conflict_type: '人物冲突',
          estimated_words: 3000
        }}
      >
        {/* 情节概要 */}
        <Form.Item
          label="情节概要"
          name="summary"
          tooltip="简要描述本章的主要情节和故事走向"
        >
          <TextArea
            rows={3}
            placeholder="简要描述本章的主要情节，例如：主角遇到意外事件，开始了一段新的冒险..."
            maxLength={500}
            showCount
          />
        </Form.Item>

        <Divider orientation="left">详细规划</Divider>

        {/* 关键事件 */}
        <Form.Item
          label="关键事件"
          tooltip="至少添加一个关键事件"
          required
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input
                placeholder="输入关键事件后按回车或点击添加"
                value={keyEventInput}
                onChange={(e) => setKeyEventInput(e.target.value)}
                onPressEnter={handleAddKeyEvent}
              />
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleAddKeyEvent}
              >
                添加
              </Button>
            </Space.Compact>
            <Space wrap>
              {keyEvents.map((event, idx) => (
                <Tag
                  key={idx}
                  closable
                  onClose={(e) => {
                    e.preventDefault();
                    setKeyEvents(keyEvents.filter((_, i) => i !== idx));
                  }}
                  color="purple"
                  style={{ marginBottom: 8 }}
                >
                  <span style={{ fontWeight: 'bold', marginRight: 4 }}>#{idx + 1}</span>
                  {event}
                </Tag>
              ))}
            </Space>
          </Space>
        </Form.Item>

        {/* 涉及角色 */}
        <Form.Item
          label="涉及角色"
          tooltip="从项目现有角色中选择"
          required
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Select
              placeholder="选择角色"
              style={{ width: '100%' }}
              loading={loadingCharacters}
              onChange={handleAddCharacter}
              value={undefined}
              showSearch
              optionFilterProp="children"
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={Array.isArray(availableCharacters)
                ? availableCharacters
                    .filter(char => !characters.includes(char.name))
                    .map(char => ({
                      label: char.name,
                      value: char.name,
                    }))
                : []}
              notFoundContent={
                loadingCharacters ? '加载中...' :
                !Array.isArray(availableCharacters) ? '加载角色失败' :
                availableCharacters.length === 0 ? '暂无角色，请先在角色管理中创建' :
                '所有角色已添加'
              }
            />
            <Space wrap>
              {characters.map((char, idx) => (
                <Tag
                  key={idx}
                  closable
                  onClose={() => setCharacters(characters.filter((_, i) => i !== idx))}
                  color="cyan"
                >
                  {char}
                </Tag>
              ))}
            </Space>
          </Space>
        </Form.Item>

        {/* 情感基调 */}
        <Form.Item
          label="情感基调"
          name="emotional_tone"
          rules={[{ required: true, message: '请输入情感基调' }]}
          tooltip="例如：紧张激烈、温馨感人、悬疑惊悚等"
        >
          <Input
            placeholder="输入情感基调，例如：紧张激烈、温馨感人等"
            maxLength={20}
          />
        </Form.Item>

        {/* 冲突类型 */}
        <Form.Item
          label="冲突类型"
          name="conflict_type"
          rules={[{ required: true, message: '请输入冲突类型' }]}
          tooltip="例如：人物冲突、内心冲突、环境冲突等"
        >
          <Input
            placeholder="输入冲突类型，例如：人物冲突、内心冲突等"
            maxLength={20}
          />
        </Form.Item>

        {/* 预估字数 */}
        <Form.Item
          label="预估字数"
          name="estimated_words"
          rules={[{ required: true, message: '请输入预估字数' }]}
        >
          <InputNumber
            min={500}
            max={10000}
            step={100}
            style={{ width: '100%' }}
            formatter={(value) => `${value} 字`}
            parser={(value) => Number(value?.replace(' 字', '')) as 500 | 10000}
          />
        </Form.Item>

        {/* 叙事目标 */}
        <Form.Item
          label="叙事目标"
          name="narrative_goal"
          rules={[{ required: true, message: '请输入叙事目标' }]}
        >
          <TextArea
            rows={3}
            placeholder="描述本章要达成的叙事目标，例如：推进主线剧情、深化角色关系、揭示重要信息等..."
            maxLength={500}
            showCount
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}